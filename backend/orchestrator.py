from .config import VOICE_ID, LANGUAGE
import logging
import requests
from .session_store import sessions

logger = logging.getLogger("sommelier")

def start_avatar_session():
    """
    Devuelve la primera sesión registrada en el diccionario sessions.
    """
    if sessions:
        sid, token = next(iter(sessions.items()))
        logger.info(f"Avatar session reused. session_id={sid}, token={token}")
        return {"session_id": sid, "token": token}
    else:
        logger.warning("No hay sesiones registradas todavía.")
        return {"session_id": None, "token": None}

def say(session_id: str, text: str):
    """
    Envía texto al avatar usando el endpoint /v1/streaming.task.
    """
    access_token = sessions.get(session_id)
    if not access_token:
        return {"error": "invalid_session", "details": "No se encontró access_token para esa sesión"}

    payload = {
        "text": text,
        "session_id": session_id,
        "task_type": "talk",
        "task_mode": "async"
    }
    try:
        resp = requests.post(
            "https://api.heygen.com/v1/streaming.task",
            headers={"x-api-key": access_token},
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Texto enviado a sesión {session_id}: {text}")
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"heygen speak failed: {e}")
        return {"error": "heygen_speak_failed", "details": str(e)}
