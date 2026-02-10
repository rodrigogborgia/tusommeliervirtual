"""
Script para probar POST /v1/sessions/token de Live Avatar.
Ejecutar desde la raíz del repo: python backend/test_liveavatar_token.py
Muestra la respuesta (200 o 422) para depurar.
"""
import os
import sys
import json
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(REPO_ROOT, "env")
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("LIVEAVATAR_API_KEY")
AVATAR_ID = os.getenv("AVATAR_ID", "Dexter_Lawyer_Sitting_public")
VOICE_ID = os.getenv("VOICE_ID", "1a32e06dde934e69ba2a98a71675dc16")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

def lang_code(l):
    if not l: return "es"
    lower = l.strip().lower()
    if "spanish" in lower or lower in ("es", "español"): return "es"
    if "english" in lower or lower == "en": return "en"
    return "es"

if not API_KEY:
    print("Falta LIVEAVATAR_API_KEY en env")
    sys.exit(1)

url = "https://api.liveavatar.com/v1/sessions/token"
headers = {"X-API-KEY": API_KEY, "Content-Type": "application/json", "Accept": "application/json"}
body = {
    "mode": "FULL",
    "avatar_id": AVATAR_ID,
    "avatar_persona": {"voice_id": VOICE_ID, "language": lang_code(LANGUAGE)},
}

print("Request body:", json.dumps(body, indent=2))
r = requests.post(url, headers=headers, json=body, timeout=15)
print("Status:", r.status_code)
print("Response:", r.text[:2000] if len(r.text) > 2000 else r.text)
if r.status_code != 200:
    try:
        print("JSON:", json.dumps(r.json(), indent=2))
    except Exception:
        pass
