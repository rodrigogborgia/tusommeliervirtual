import os
import requests
import logging
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from dotenv import load_dotenv
from pydantic import BaseModel

# --- Nuestros módulos internos ---
from app_flow import main as run_flow
from session_store import sessions
from orchestrator import say

# --- Configuración ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sommelier")

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
AVATAR_ID = os.getenv("AVATAR_ID")
VOICE_ID = os.getenv("VOICE_ID")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

# --- FastAPI ---
app = FastAPI()


class SpeakRequest(BaseModel):
    session_id: str
    text: str

# --- Endpoints básicos ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/session/start")
def start_session():
    """
    Crea un token de streaming en HeyGen y devuelve parámetros al front.
    """
    if not HEYGEN_API_KEY:
        return JSONResponse({"error": "missing_api_key"}, status_code=500)

    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {"Authorization": f"Bearer {HEYGEN_API_KEY}", "accept": "application/json"}

    try:
        r = requests.post(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        token = data.get("token")
    except Exception as e:
        return JSONResponse({"error": "heygen_create_token_failed", "details": str(e)}, status_code=502)

    logger.info(f"Token creado: {token}")

    return {
        "token": token,
        "avatar_id": AVATAR_ID,
        "voice_id": VOICE_ID,
        "language": LANGUAGE
    }

@app.post("/api/session/register")
def register_session(req: dict):
    """
    Guarda el access_token asociado a una sesión de avatar.
    """
    sid = req.get("session_id")
    token = req.get("access_token")
    if sid and token:
        sessions[sid] = token
        return {"status": "ok"}
    return {"status": "error", "details": "faltan datos"}

@app.post("/api/query")
async def query_endpoint(request: Request):
    """
    Recibe {mode, query} desde el front end.
    Ejecuta la lógica Entrenar/Presentar/Confirmar y devuelve la respuesta.
    """
    data = await request.json()
    mode = data.get("mode", "Presentar")
    query = data.get("query", "")

    if not query:
        return JSONResponse({"respuesta": "No se recibió ninguna consulta."})

    return run_flow(mode=mode, query=query, response=data.get("response"), correction=data.get("correction"))

@app.post("/api/speak")
def speak(req: SpeakRequest):
    """
    Envía texto al avatar vía HeyGen.
    """
    if not req.session_id or not req.text:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    access_token = sessions.get(req.session_id)
    if not access_token:
        return JSONResponse({"error": "invalid_session"}, status_code=400)

    try:
        payload = {
            "text": req.text,
            "session_id": req.session_id,
            "task_type": "talk",
            "task_mode": "async"
        }
        resp = requests.post(
            "https://api.heygen.com/v1/streaming.task",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Texto enviado a sesión {req.session_id}: {req.text}")
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"heygen speak failed: {e}")
        return JSONResponse({"error": "heygen_speak_failed", "details": str(e)}, status_code=500)

@app.get("/api/routes")
def list_routes():
    return [{"path": route.path, "methods": list(route.methods)} for route in app.router.routes if isinstance(route, APIRoute)]

# --- Servir frontend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    logger.warning(f"Frontend dist dir not found: {FRONTEND_DIST_DIR}")
