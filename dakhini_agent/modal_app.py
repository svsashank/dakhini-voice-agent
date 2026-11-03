"""Everything that needs a secret or a GPU runs here, on Modal.

Secrets (created once with `modal secret create`, never stored in the repo):
  openrouter -> OPENROUTER_API_KEY
  huggingface -> HF_TOKEN
"""
import json
import modal

from . import config

app = modal.App(config.MODAL_APP)

llm_image = modal.Image.debian_slim(python_version="3.11").pip_install("openai>=1.40")
hf_image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub")
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper==1.1.1", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*")
    .env({"LD_LIBRARY_PATH": "/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:"
                             "/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib"})
)
model_cache = modal.Volume.from_name("dakhini-whisper-cache", create_if_missing=True)

openrouter_secret = modal.Secret.from_name(config.OPENROUTER_SECRET)
hf_secret = modal.Secret.from_name(config.HF_SECRET)


def _llm():
    import os
    from openai import OpenAI
    return OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])


def _json_from(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [0]), max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start:end + 1])


@app.function(image=llm_image, secrets=[openrouter_secret], timeout=120)
def generate_queries(n: int, avoid: list[str]) -> list[str]:
    """Ask the LLM for fresh YouTube / podcast search queries."""
    prompt = (
        f"I am collecting natural spoken Hyderabadi / Dakhini (Deccani Urdu) audio: "
        f"conversations, interviews, podcasts, standup, vlogs, storytelling, street talk.\n"
        f"Generate {n} diverse search queries (mix English, Hinglish/Roman Urdu, and Urdu/Hindi "
        f"script) for finding such audio on YouTube and podcast directories. "
        f"Avoid music, movies, recipes. Do not repeat these already-used queries: {avoid[-40:]}.\n"
        f"Return ONLY a JSON array of strings."
    )
    r = _llm().chat.completions.create(
        model=config.LLM_MODEL, temperature=0.9,
        messages=[{"role": "user", "content": prompt}])
    qs = _json_from(r.choices[0].message.content)
    return [q.strip() for q in qs if isinstance(q, str) and q.strip()][:n]


@app.cls(image=gpu_image, gpu=config.GPU, timeout=600, scaledown_window=120,
         volumes={"/cache": model_cache})
class Transcriber:
    @modal.enter()
    def load(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(config.WHISPER_MODEL, device="cuda",
                                  compute_type="float16", download_root="/cache")
        model_cache.commit()

    @modal.method()
    def transcribe(self, audio: bytes) -> dict:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            f.write(audio)
            f.flush()
            # Language auto-detect; Dakhini is usually detected as Urdu or Hindi.
            segs, info = self.model.transcribe(f.name, beam_size=5, vad_filter=True)
            text = " ".join(s.text.strip() for s in segs)
        return {"text": text, "language": info.language,
                "language_probability": float(info.language_probability)}


JUDGE_PROMPT = """You are a linguist expert in Hyderabadi / Dakhini (Deccani) Urdu.
Below is a Whisper transcript of a 30-second audio clip (Whisper may normalise or mangle
dialect words, so be tolerant). Detected language: {lang} (p={prob:.2f}).
Title: {title}
Transcript:
\"\"\"{text}\"\"\"

Dakhini markers include: nakko / nako (don't want), hau / haan (yes), kaiku / kyun-ku (why),
kidhar / kaiko, mereku / tereku / usku (to me/you/him: -ku dative), jaara / aara / kar ra / bol ra
(contracted progressive "-ra"), nai / nei (no), baat-chit with "bhai", "miyan", "baigan" jokes,
"hyderabadi" Telugu-influenced words (e.g. "gadha", "hallu"), "pakdo", "samjha kya".

Decide whether this clip contains genuine spoken Dakhini/Hyderabadi speech
(not standard Hindi/Urdu, not just a Hyderabad-related title, not music).
Return ONLY JSON: {{"is_dakhini": bool, "confidence": 0-1, "markers": [strings], "reason": str}}"""


@app.function(image=llm_image, secrets=[openrouter_secret], timeout=120)
def judge_dakhini(title: str, transcript: dict) -> dict:
    if len(transcript["text"].split()) < 8:
        return {"is_dakhini": False, "confidence": 0.0, "markers": [],
                "reason": "transcript too short / no speech"}
    prompt = JUDGE_PROMPT.format(lang=transcript["language"],
                                 prob=transcript["language_probability"],
                                 title=title, text=transcript["text"][:3000])
    r = _llm().chat.completions.create(
        model=config.LLM_MODEL, temperature=0,
        messages=[{"role": "user", "content": prompt}])
    return _json_from(r.choices[0].message.content)


@app.function(image=hf_image, secrets=[hf_secret], timeout=1800)
def upload_to_hf(repo_id: str, filename: str, audio: bytes, metadata: dict) -> str:
    """Upload audio + a metadata json to a *private* dataset repo (created if missing)."""
    import io
    import os
    from huggingface_hub import HfApi
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
    stem = filename.rsplit(".", 1)[0]
    api.upload_file(path_or_fileobj=io.BytesIO(audio), path_in_repo=f"audio/{filename}",
                    repo_id=repo_id, repo_type="dataset")
    api.upload_file(path_or_fileobj=io.BytesIO(json.dumps(metadata, ensure_ascii=False, indent=2).encode()),
                    path_in_repo=f"metadata/{stem}.json", repo_id=repo_id, repo_type="dataset")
    return f"{repo_id}/audio/{filename}"
