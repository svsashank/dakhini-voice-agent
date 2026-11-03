"""Static configuration. No secrets live here: OPENROUTER_API_KEY and HF_TOKEN
exist only as Modal secrets (see README)."""
import os

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Any OpenRouter model id works; override with DAKHINI_LLM.
LLM_MODEL = os.environ.get("DAKHINI_LLM", "anthropic/claude-sonnet-4.5")

WHISPER_MODEL = "large-v3"
GPU = "L4"

MODAL_APP = "dakhini-voice-agent"
OPENROUTER_SECRET = "openrouter"      # contains OPENROUTER_API_KEY
HF_SECRET = "huggingface"             # contains HF_TOKEN

SAMPLE_SECONDS = 30
SAMPLE_OFFSET_SECONDS = 60            # skip intros
MIN_DURATION_S = 120                  # full audio bounds
MAX_DURATION_S = 3 * 3600
MAX_FULL_DOWNLOAD_MB = 400

POSITIVE_TERMS = [
    "dakhini", "dakhni", "dakkhini", "deccani", "dakani", "hyderabadi",
    "hyderabad", "nizam", "old city", "charminar", "hyderabadi urdu",
    "दक्खिनी", "दखनी", "हैदराबादी", "دکنی", "حیدرآبادی",
]
NEGATIVE_TERMS = [
    "recipe", "biryani recipe", "trailer", "full movie", "lyrics",
    "ringtone", "status video", "shorts", "asmr", "news live",
]
