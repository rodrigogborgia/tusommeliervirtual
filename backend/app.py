import os
import requests
import logging
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

# Variables de entorno (se cargan desde .env)
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
DEXTER_AVATAR_ID = os.getenv("DEXTER_AVATAR_ID")
VOICE_ID = os.getenv("VOICE_ID")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

app = FastAPI()

# --- Ajuste para frontend al mismo nivel que backend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# --- Endpoints del backend bajo prefijo /api ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/session/start")
def start_session():
    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {
        "x-api-key": HEYGEN_API_KEY,
        "accept": "application/json",
        "content-type": "application/json"
    }
    payload = {
        "avatarName": DEXTER_AVATAR_ID,
        "voiceId": VOICE_ID,
        "language": LANGUAGE,
        "quality": "high",
        "video": True
    }

    logging.info(f"Payload enviado a HeyGen: {payload}")

    r = requests.post(url, headers=headers, json=payload)
    logging.info(f"Response status: {r.status_code}")
    logging.info(f"Response text: {r.text}")

    if r.status_code == 200:
        data = r.json().get("data", {})
        return JSONResponse({
            "data": data,
            "avatar_id": DEXTER_AVATAR_ID,
            "voice_id": VOICE_ID,
            "language": LANGUAGE
        })
    else:
        return JSONResponse({"error": r.text}, status_code=r.status_code)

@app.get("/api/stt/transcribe_file")
def transcribe_file(file_path: str = Query(..., description="Ruta del archivo de audio RAW")):
    # TODO: integrar con Vosk WebSocket o cliente local
    return {"file_path": file_path, "transcription": "Transcripción simulada"}

@app.get("/api/routes")
def list_routes():
    return [{"path": r.path, "methods": list(r.methods)} for r in app.router.routes]

# 👉 Servir el build de Vite en la raíz (al final)
app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
