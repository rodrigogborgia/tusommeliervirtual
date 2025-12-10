import os
from dotenv import load_dotenv

load_dotenv()  # carga variables desde .env

# --- HeyGen ---
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
AVATAR_ID = os.getenv("AVATAR_ID", "")
VOICE_ID = os.getenv("VOICE_ID", "")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- STT (Vosk WebSocket) ---
STT_WS_URL = os.getenv("STT_WS_URL", "ws://127.0.0.1:2700")
STT_SAMPLE_RATE = int(os.getenv("STT_SAMPLE_RATE", "16000"))
