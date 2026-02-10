import os
from dotenv import load_dotenv

_repo_root = os.path.join(os.path.dirname(__file__), '..')
_env_candidates = [
    os.getenv("ENV_PATH"),
    os.path.join(_repo_root, "env"),
    os.path.join(_repo_root, ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(dotenv_path=_p)
        break
else:
    load_dotenv()

# --- Live Avatar ---
LIVEAVATAR_API_KEY = os.getenv("LIVEAVATAR_API_KEY", "")
LIVEAVATAR_API_URL = os.getenv("LIVEAVATAR_API_URL", "https://api.liveavatar.com")

# --- Avatar (compartido: LiveAvatar usa estos si están definidos) ---
AVATAR_ID = os.getenv("AVATAR_ID", "")
VOICE_ID = os.getenv("VOICE_ID", "")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- STT (Vosk WebSocket) ---
STT_WS_URL = os.getenv("STT_WS_URL", "ws://127.0.0.1:2700")
STT_SAMPLE_RATE = int(os.getenv("STT_SAMPLE_RATE", "16000"))
