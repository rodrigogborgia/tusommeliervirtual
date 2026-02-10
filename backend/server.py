import os
import requests
import logging
import json
import uuid
from starlette.websockets import WebSocketState
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI

from .app_flow import main as run_flow
from .audio_utils import is_valid_transcription
from qa_log import QALog

qa_logger = QALog()

# --- Configuración ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_env():
    # Prioridad: ENV_PATH explícito -> env/.env del repo -> path de producción en /opt -> defaults del entorno
    candidates = [
        os.getenv("ENV_PATH"),
        os.path.join(REPO_ROOT, "env"),
        os.path.join(REPO_ROOT, ".env"),
        "/opt/tusommeliervirtual.com/.env",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            load_dotenv(dotenv_path=p)
            return p
    load_dotenv()
    return None

_ENV_LOADED_FROM = _load_env()

def _get_log_file() -> str:
    # Permite override por env vars, y evita rutas Linux en Windows.
    if os.getenv("LOG_FILE"):
        return os.getenv("LOG_FILE")
    log_dir = os.getenv("LOG_DIR")
    if not log_dir:
        log_dir = os.path.join(REPO_ROOT, "logs") if os.name == "nt" else "/var/log/sommelier"
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = os.path.join(REPO_ROOT, "logs")
        os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "qa_performance.log")

logging.basicConfig(
    filename=_get_log_file(),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sommelier")

LIVEAVATAR_API_KEY = os.getenv("LIVEAVATAR_API_KEY")
LIVEAVATAR_API_URL = os.getenv("LIVEAVATAR_API_URL", "https://api.liveavatar.com")
AVATAR_ID = os.getenv("AVATAR_ID", "fc9c1f9f-bc99-4fd9-a6b2-8b4b5669a046")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PIPELINE_NAME = os.getenv("PIPELINE_NAME", "unknown-pipeline")
BUILD_ID = os.getenv("BUILD_ID", "unknown-build")
COMMIT_SHA = os.getenv("COMMIT_SHA", "unknown-commit")

# --- Cliente OpenAI (opcional para permitir levantar sin secrets en dev) ---
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 👉 logs de entorno solo al arrancar
    logger.info(f"ENV cargado desde: {_ENV_LOADED_FROM or 'entorno'}")
    logger.info(f"LIVEAVATAR_API_KEY presente: {bool(LIVEAVATAR_API_KEY)}")
    logger.info(f"OPENAI_API_KEY presente: {bool(OPENAI_API_KEY)}")
    logger.info(f"AVATAR_ID={AVATAR_ID}, LANGUAGE={LANGUAGE}")
    logger.info(f"PIPELINE_NAME={PIPELINE_NAME}, BUILD_ID={BUILD_ID}, COMMIT_SHA={COMMIT_SHA}")
    yield
    # 👉 acá podrías poner cleanup al apagar

app = FastAPI(lifespan=lifespan)

# --- BASE_DIR para frontend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# --- Modelos de request ---
class SpeakRequest(BaseModel):
    session_id: str
    text: str

# --- Endpoints REST ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

def _language_code(lang: str) -> str:
    """Mapea LANGUAGE a código para LiveAvatar (es, en, etc.)."""
    if not lang:
        return "es"
    lower = lang.strip().lower()
    if "spanish" in lower or lower == "es" or lower == "español":
        return "es"
    if "english" in lower or lower == "en":
        return "en"
    return "es"


@app.post("/api/session/start")
def start_session():
    if not (LIVEAVATAR_API_KEY and LIVEAVATAR_API_KEY.strip()):
        return JSONResponse(
            {"error": "missing_api_key", "details": "LIVEAVATAR_API_KEY es requerida en env"},
            status_code=500,
        )
    url = f"{LIVEAVATAR_API_URL.rstrip('/')}/v1/sessions/token"
    headers = {
        "X-API-KEY": LIVEAVATAR_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "mode": "FULL",
        "avatar_id": AVATAR_ID,
    }
    body["avatar_persona"] = {
        "language": _language_code(LANGUAGE),
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15)
        if r.status_code != 200:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text or str(r.status_code)
            logger.error(f"LiveAvatar API error {r.status_code}: {err_body}")
            hint = ""
            if r.status_code == 422 and "avatar_id" in str(err_body).lower() and "uuid" in str(err_body).lower():
                hint = " En Live Avatar, AVATAR_ID debe ser un UUID de tu cuenta en app.liveavatar.com."
            return JSONResponse(
                {
                    "error": "liveavatar_create_token_failed",
                    "details": err_body,
                    "hint": hint.strip() or None,
                    "status_code": r.status_code,
                },
                status_code=502,
            )
        data = r.json()
        token = None
        if isinstance(data.get("data"), dict):
            token = data["data"].get("token") or data["data"].get("session_token")
        if not token:
            token = data.get("token") or data.get("session_token")
        if not token:
            logger.error(f"LiveAvatar token response sin token: {list(data.keys())}")
            return JSONResponse(
                {"error": "invalid_session_data", "details": "no token in response"},
                status_code=500,
            )
        logger.info(f"LiveAvatar /v1/sessions/token OK, token_len={len(str(token))}")
        start_url = f"{LIVEAVATAR_API_URL.rstrip('/')}/v1/sessions/start"
        start_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        r_start = requests.post(start_url, headers=start_headers, timeout=15)
        try:
            start_data = r_start.json()
        except Exception:
            start_data = {}
        info = start_data.get("data") or start_data
        # Algunas versiones de la API devuelven 200 con code en cuerpo, o datos útiles con otro status
        if r_start.status_code != 200:
            # Si aun así trae datos de sesión (p. ej. code 1000 = éxito en cuerpo), intentar usarlos
            livekit_url = info.get("livekit_url")
            livekit_client_token = info.get("livekit_client_token")
            session_id = info.get("session_id")
            if livekit_url and livekit_client_token:
                logger.info(f"LiveAvatar start: HTTP {r_start.status_code} pero body con sesión OK, session_id={session_id}")
            else:
                logger.error(f"LiveAvatar /v1/sessions/start error {r_start.status_code}: {start_data}")
                return JSONResponse(
                    {
                        "error": "liveavatar_start_failed",
                        "details": start_data.get("message") or start_data.get("error") or str(r_start.status_code),
                        "status_code": r_start.status_code,
                    },
                    status_code=502,
                )
        else:
            session_id = info.get("session_id")
        livekit_url = info.get("livekit_url")
        livekit_client_token = info.get("livekit_client_token")
        session_id = info.get("session_id")
        if not livekit_url or not livekit_client_token:
            logger.error(f"LiveAvatar start sin livekit_url/token: {list(info.keys())}")
            return JSONResponse(
                {"error": "invalid_session_data", "details": "no livekit_url or livekit_client_token"},
                status_code=500,
            )
        logger.info(f"LiveAvatar /v1/sessions/start OK, session_id={session_id}")
        return {
            "token": livekit_client_token,
            "session_id": None,
            "prestarted": True,
            "livekit_url": livekit_url,
            "livekit_client_token": livekit_client_token,
            "liveavatar_session_id": session_id,
            "avatar_id": AVATAR_ID,
            "language": _language_code(LANGUAGE),
        }
    except requests.RequestException as e:
        logger.error(f"Error creando token de LiveAvatar: {e}")
        return JSONResponse(
            {"error": "liveavatar_create_token_failed", "details": str(e)},
            status_code=502,
        )

class QALogRequest(BaseModel):
    query: str
    response: str
    correction: str | None = None
    metrics: dict | None = None


@app.post("/api/query")
async def query_endpoint(request: Request):
    data = await request.json()
    mode = data.get("mode", "Presentar")
    query = data.get("query", "")
    if not query:
        return JSONResponse({"respuesta": "No se recibió ninguna consulta."})
    if not OPENAI_API_KEY:
        return JSONResponse({"error": "missing_openai_api_key"}, status_code=500)

    # skip_save=True: el frontend enviará métricas completas vía /api/qa/log
    res = run_flow(
        mode=mode,
        query=query,
        response=data.get("response"),
        correction=data.get("correction"),
        skip_save=True,
    )

    respuesta_texto = res.get("respuesta", "")
    llm_time_ms = res.get("llm_time_ms")

    logger.info(f"Respuesta generada en /api/query: {respuesta_texto}")

    out = {"respuesta": respuesta_texto}
    if llm_time_ms is not None:
        out["llm_time_ms"] = llm_time_ms
    return out


@app.post("/api/qa/log")
def qa_log_endpoint(req: QALogRequest):
    """Recibe métricas completas del frontend y las guarda en qa_log.jsonl."""
    qa_logger.save_interaction(
        query=req.query,
        response=req.response,
        correction=req.correction,
        client_metrics=req.metrics if req.metrics is not None else {},
    )
    return {"status": "ok"}

@app.post("/api/speak")
def speak(req: SpeakRequest):
    # 👉 Ya no usamos access_token ni llamamos a streaming.task
    if not req.text:
        return JSONResponse({"error": "missing_text"}, status_code=400)

    logger.info(f"Texto recibido en /api/speak para sesión {req.session_id}: {req.text}")

    # 👉 El backend solo devuelve el texto, el frontend dispara la voz con avatar.addTask
    return {"status": "ok", "text": req.text}

# --- WebSocket de audio ---
@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket):
    print("🔌 [WS] Conexión entrante en /ws/audio")
    await websocket.accept()
    print("✅ [WS] Cliente WebSocket ACEPTADO")
    logger.info("Cliente WS conectado para audio")

    try:
        while True:
            message = await websocket.receive()

            # --- Caso: mensaje de control (texto JSON) ---
            if "text" in message:
                try:
                    payload = json.loads(message["text"])
                    print(f"📨 [WS] Mensaje recibido: {payload}")
                    logger.info(f"WS control recibido: {payload}")

                    if payload.get("type") == "mark":
                        qa_logger.mark(payload.get("label"))

                    # 👉 Transcripción desde el browser (Web Speech API)
                    elif payload.get("type") == "transcript":
                        text = (payload.get("text") or "").strip()
                        print(f"[BROWSER_STT] text={text!r}")
                        logger.info(f"Transcripción del browser: {text}")
                        
                        if is_valid_transcription(text):
                            qa_logger.mark("stt_start")
                            respuesta = run_flow(mode="Presentar", query=text)
                            qa_logger.mark("stt_done")
                            qa_logger.diff("stt_start", "stt_done")
                            
                            respuesta_texto = respuesta.get("respuesta", "")
                            logger.info(f"Respuesta generada: {respuesta_texto}")
                            
                            # Enviar respuesta al frontend (formato compatible con main.js)
                            try:
                                if websocket.application_state == WebSocketState.CONNECTED:
                                    await websocket.send_text(json.dumps({
                                        "type": "llm_response",
                                        "user_text": text,
                                        "bot_text": respuesta_texto
                                    }))
                                else:
                                    logger.info("WS ya cerrado, no se envía respuesta")
                            except WebSocketDisconnect:
                                logger.info("WS desconectado al intentar enviar respuesta")
                        else:
                            logger.info(f"Transcripción del browser descartada: {text}")

                except Exception as e:
                    logger.warning(f"Texto WS no válido: {message['text']} ({e})")

            # --- Caso: desconexión ---
            elif message.get("type") == "websocket.disconnect":
                logger.info("Cliente WS desconectado")
                break

    except WebSocketDisconnect:
        logger.info("Cliente WS desconectado")
    except Exception as e:
        logger.exception(f"Error en WS audio: {e}")
        # Evitamos crash: solo cerramos si sigue abierto
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()
        else:
            logger.info("WS ya estaba cerrado, no se envía nada más")

# --- Listado de rutas ---
@app.get("/api/routes")
def list_routes():
    return [{"path": route.path, "methods": list(route.methods)}
            for route in app.router.routes if isinstance(route, APIRoute)]

# --- Página debug (STT browser events) ---
# Debe ir ANTES del mount de StaticFiles para que FastAPI la registre antes del catch-all.
@app.get("/stt.html")
def stt_browser_debug_page():
    """
    Sirve el stt.html de la raíz del repo para pruebas rápidas en http://localhost.
    Importante: SpeechRecognition suele requerir contexto seguro o localhost.
    """
    p = os.path.join(REPO_ROOT, "stt.html")
    if not os.path.exists(p):
        return JSONResponse({"error": "stt_html_not_found", "path": p}, status_code=404)
    return FileResponse(p, media_type="text/html")

# --- Servir frontend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    logger.warning("Frontend dist dir not found. Ejecutá `npm run build` en frontend/")
