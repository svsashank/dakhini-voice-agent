# dakhini-voice-agent

Agent that collects Hyderabadi / Dakhini speech audio into a **private** Hugging Face dataset.

Pipeline: OpenRouter LLM generates search queries → yt-dlp (YouTube) + iTunes/RSS (podcasts) →
title/description filter → 30 s sample → Whisper large-v3 on a Modal GPU → LLM judges whether the
transcript is Dakhini → full audio downloaded and uploaded (audio + metadata json).

Anything needing a key (OpenRouter, Hugging Face) or a GPU runs on Modal; keys live only in Modal secrets.

## Setup
```bash
pip install -r requirements.txt   # also needs ffmpeg
modal setup
modal secret create openrouter OPENROUTER_API_KEY=...
modal secret create huggingface HF_TOKEN=...      # needs write access
```
## Run
```bash
python -m dakhini_agent --repo YOUR_HF_USER/dakhini-audio --dry-run   # stop before upload
python -m dakhini_agent --repo YOUR_HF_USER/dakhini-audio
```
Set `DAKHINI_LLM` to change the OpenRouter model. `state.json` (gitignored) remembers queries/seen items.
