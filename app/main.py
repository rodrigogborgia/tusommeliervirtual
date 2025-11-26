import os
from fastapi import FastAPI, File, UploadFile, Form
import requests

app = FastAPI()

VOSK_URL = "http://localhost:2700"
HEYGEN_API_URL = "https://api.heygen.com/v1/video.generate"
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")  # se lee de variable de entorno

@app.post("/ask")
async def ask(lang: str = Form(...), audio: UploadFile = File(...)):
    files = {"audio": (audio.filename, await audio.read(), audio.content_type)}
    data = {"lang": lang}
    vosk_resp = requests.post(VOSK_URL, files=files, data=data)
    transcript = vosk_resp.json().get("text", "")

    response_text = f"Tú dijiste: {transcript}"

    heygen_payload = {
        "text": response_text,
        "voice": "en_us_male1",
        "avatar": "default",
    }
    headers = {"Authorization": f"Bearer {HEYGEN_API_KEY}"}
    heygen_resp = requests.post(HEYGEN_API_URL, json=heygen_payload, headers=headers)

    return {
        "transcript": transcript,
        "response_text": response_text,
        "heygen_result": heygen_resp.json()
    }

