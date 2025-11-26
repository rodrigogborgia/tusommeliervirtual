import requests
from config import HEYGEN_API_KEY, LANGUAGE

BASE = "https://api.heygen.com/v1"
TIMEOUT = 30

def _headers():
    return {"Authorization": f"Bearer {HEYGEN_API_KEY}", "Content-Type": "application/json"}

def open_session(avatar_id: str, interactive: bool = True):
    payload = {"avatar_id": avatar_id, "interactive": interactive}
    r = requests.post(f"{BASE}/avatar/session", json=payload, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()  # espera: {"session_id": "...", ...}

def speak_text(session_id: str, text: str, voice_id: str, language: str = LANGUAGE):
    payload = {
        "session_id": session_id,
        "text": text,
        "voice_id": voice_id,
        "language": language,
        "interactive": True
    }
    r = requests.post(f"{BASE}/avatar/speak", json=payload, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
