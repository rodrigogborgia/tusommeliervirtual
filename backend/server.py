import os
import requests
import logging
import json
import uuid
from starlette.websockets import WebSocketState
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI

from .app_flow import main as run_flow
from .session_store import sessions
from .audio_utils import AudioBuffer, pcm_to_wav, is_valid_transcription, should_transcribe_phrase
from .stt_local import transcribe_pcm16_phrase
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

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
AVATAR_ID = os.getenv("AVATAR_ID", "Dexter_Lawyer_Sitting_public")
VOICE_ID = os.getenv("VOICE_ID", "1a32e06dde934e69ba2a98a71675dc16")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PIPELINE_NAME = os.getenv("PIPELINE_NAME", "unknown-pipeline")
BUILD_ID = os.getenv("BUILD_ID", "unknown-build")
COMMIT_SHA = os.getenv("COMMIT_SHA", "unknown-commit")

# --- Cliente OpenAI (opcional para permitir levantar sin secrets en dev) ---
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
STT_MODE = (os.getenv("STT_MODE") or "openai").strip().lower()

from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 👉 logs de entorno solo al arrancar
    logger.info(f"ENV cargado desde: {_ENV_LOADED_FROM or 'entorno'}")
    logger.info(f"HEYGEN_API_KEY presente: {bool(HEYGEN_API_KEY)}")
    logger.info(f"OPENAI_API_KEY presente: {bool(OPENAI_API_KEY)}")
    logger.info(f"AVATAR_ID={AVATAR_ID}, VOICE_ID={VOICE_ID}, LANGUAGE={LANGUAGE}")
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

class RegisterSessionRequest(BaseModel):
    session_id: str
    access_token: str

# --- Endpoints REST ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/session/start")
def start_session():
    if not HEYGEN_API_KEY:
        return JSONResponse({"error": "missing_api_key"}, status_code=500)

    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {
        "x-api-key": HEYGEN_API_KEY,
        "accept": "application/json"
    }
    try:
        r = requests.post(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {}) or {}
        # Evitar loguear tokens en claro
        redacted = dict(data)
        if "token" in redacted and redacted["token"]:
            redacted["token"] = f"<redacted len={len(str(redacted['token']))}>"
        logger.info(f"HeyGen /streaming.create_token OK: {redacted}")

        session_token = data.get("token")
        if not session_token:
            return JSONResponse(
                {"error": "invalid_session_data", "details": data},
                status_code=500
            )

        import uuid
        session_id = str(uuid.uuid4())
        sessions[session_id] = session_token

        # 🔎 Debug extra (sin exponer token)
        logger.info(f"[TOKEN DEBUG] Nuevo session_id={session_id}, token_len={len(session_token)}")

        return {
            "token": session_token,
            "session_id": session_id,
            "avatar_id": AVATAR_ID,
            "voice_id": VOICE_ID,
            "language": LANGUAGE
        }
    except Exception as e:
        logger.error(f"Error creando token de HeyGen: {e}")
        return JSONResponse(
            {"error": "heygen_create_token_failed", "details": str(e)},
            status_code=502
        )

@app.post("/api/session/register")
def register_session(req: RegisterSessionRequest):
    sessions[req.session_id] = req.access_token
    logger.info(f"Session {req.session_id} registrada con access_token")

    return {"status": "ok"}

@app.post("/api/query")
async def query_endpoint(request: Request):
    data = await request.json()
    mode = data.get("mode", "Presentar")
    query = data.get("query", "")
    if not query:
        return JSONResponse({"respuesta": "No se recibió ninguna consulta."})
    if not OPENAI_API_KEY:
        return JSONResponse({"error": "missing_openai_api_key"}, status_code=500)

    res = run_flow(
        mode=mode,
        query=query,
        response=data.get("response"),
        correction=data.get("correction")
    )

    # 👉 El backend ya no dispara voz, solo devuelve el texto
    respuesta_texto = res.get("respuesta", "")

    logger.info(f"Respuesta generada en /api/query: {respuesta_texto}")

    return {"respuesta": respuesta_texto}

@app.post("/api/speak")
def speak(req: SpeakRequest):
    # 👉 Ya no usamos access_token ni llamamos a streaming.task
    if not req.text:
        return JSONResponse({"error": "missing_text"}, status_code=400)

    logger.info(f"Texto recibido en /api/speak para sesión {req.session_id}: {req.text}")

    # 👉 El backend solo devuelve el texto, el frontend dispara la voz con avatar.addTask
    return {"status": "ok", "text": req.text}

# --- Función auxiliar para procesar audio ---
async def procesar_audio_phrase(websocket: WebSocket, phrase: bytes):
    qa_logger.mark("stt_start")
    ok, metrics = should_transcribe_phrase(phrase)
    if not ok:
        # Debug a consola: si no ves [STT_CALL], probablemente estás cayendo acá (frase muy corta o muy silenciosa).
        try:
            print(
                f"[STT_SKIP] mode={STT_MODE} bytes={len(phrase)} "
                f"dur={metrics.get('duration_sec', 0.0):.2f}s "
                f"rms={metrics.get('rms', 0.0):.1f} peak={metrics.get('peak', 0.0):.0f}"
            )
        except Exception:
            pass
        logger.info(
            f"Frase descartada antes de Whisper (probable silencio/ruido): "
            f"dur={metrics['duration_sec']:.2f}s rms={metrics['rms']:.1f} peak={metrics['peak']}"
        )
        return

    try:
        # Debug a consola: correlaciona audio->transcripción con un phrase_id,
        # y opcionalmente guarda el WAV exacto enviado a STT.
        phrase_id = uuid.uuid4().hex[:10]
        try:
            dur = float(metrics.get("duration_sec", 0.0))
            rms = float(metrics.get("rms", 0.0))
            peak = float(metrics.get("peak", 0.0))
        except Exception:
            dur, rms, peak = 0.0, 0.0, 0.0

        debug_save_wav = (os.getenv("STT_DEBUG_SAVE_WAV") or "").strip().lower() in ("1", "true", "yes", "y")
        debug_wav_path = None
        if debug_save_wav:
            try:
                repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                wav_dir = (os.getenv("STT_DEBUG_WAV_DIR") or os.path.join(repo_root, "logs", "stt_audio")).strip()
                os.makedirs(wav_dir, exist_ok=True)
                debug_wav_path = os.path.join(wav_dir, f"phrase_{phrase_id}.wav")
                with open(debug_wav_path, "wb") as f:
                    f.write(pcm_to_wav(phrase).read())
            except Exception as e:
                logger.warning(f"No se pudo guardar WAV de debug: {e}")
                debug_wav_path = None

        print(
            f"[STT_CALL] id={phrase_id} mode={STT_MODE} bytes={len(phrase)} "
            f"dur={dur:.2f}s rms={rms:.1f} peak={peak:.0f}"
            + (f" wav='{debug_wav_path}'" if debug_wav_path else "")
        )

        if STT_MODE == "local":
            text = (transcribe_pcm16_phrase(phrase) or "").strip()
            qa_logger.mark("stt_done")
            qa_logger.diff("stt_start", "stt_done")
            logger.info(f"Transcripción faster-whisper: {text}")
        else:
            wav_buf = pcm_to_wav(phrase)
            if not client:
                raise RuntimeError("OPENAI_API_KEY no configurada (necesaria para transcribir con Whisper)")
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_buf,
                language="es",
                temperature=0.0
            )
            qa_logger.mark("stt_done")
            qa_logger.diff("stt_start", "stt_done")

            text = (transcript.text or "").strip()
            logger.info(f"Transcripción Whisper: {text}")

        # Resultado a consola (para debug rápido)
        print(f"[STT_RESULT] id={phrase_id} text={text!r}")

        if is_valid_transcription(text):
            respuesta = run_flow(mode="Presentar", query=text)
            respuesta_texto = respuesta.get("respuesta", "")

            # 👉 Enviar solo el texto y la respuesta al frontend
            try:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps({
                        "text": text,
                        "respuesta": respuesta_texto
                    }))
                else:
                    logger.info("WS ya cerrado, no se envía respuesta")
            except WebSocketDisconnect:
                logger.info("WS desconectado al intentar enviar respuesta")

        else:
            logger.info(f"Transcripción descartada: {text}")

    except Exception as e:
        logger.error(f"Transcripción fallida: {e}")
        try:
            print(f"[STT_ERROR] id={phrase_id} err={str(e)!r}")
        except Exception:
            pass
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({
                    "error": "transcription_failed",
                    "details": str(e)
                }))
            else:
                logger.info("WS ya cerrado, no se envía mensaje de error")
        except WebSocketDisconnect:
            logger.info("WS desconectado al intentar enviar mensaje de error")

# --- WebSocket de audio ---
@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket):
    print("🔌 [WS] Conexión entrante en /ws/audio")
    await websocket.accept()
    print("✅ [WS] Cliente WebSocket ACEPTADO")
    logger.info("Cliente WS conectado para audio")

    audio_buffer = AudioBuffer()

    try:
        while True:
            message = await websocket.receive()

            # --- Caso: audio binario ---
            if "bytes" in message:
                data = message["bytes"]

                if not data:
                    qa_logger.mark("interaction_start")
                    qa_logger.mark("audio_received")
                    phrase = audio_buffer.flush()
                    if phrase:
                        await procesar_audio_phrase(websocket, phrase)
                    continue

                phrase = audio_buffer.add_chunk(data)
                if phrase:
                    qa_logger.mark("interaction_start")
                    qa_logger.mark("audio_received")
                    await procesar_audio_phrase(websocket, phrase)

            # --- Caso: mensaje de control (texto JSON) ---
            elif "text" in message:
                try:
                    payload = json.loads(message["text"])
                    print(f"📨 [WS] Mensaje recibido: {payload}")
                    logger.info(f"WS control recibido: {payload}")

                    if payload.get("type") == "mark":
                        qa_logger.mark(payload.get("label"))

                    elif payload.get("type") == "register":
                        websocket.session_id = payload.get("session_id")
                        access_token = payload.get("access_token")
                        mode = payload.get("mode", "whisper")  # 👈 Detectar modo browser_stt
                        logger.info(
                            f"WS REGISTER recibido: session_id={websocket.session_id}, "
                            f"access_token_presente={bool(access_token)}, mode={mode}"
                        )
                        if access_token:
                            sessions[websocket.session_id] = access_token
                            logger.info(f"Session {websocket.session_id} registrada con access_token")

                    # 👉 Nuevo caso: transcripción desde el browser (sin pasar por Whisper)
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
