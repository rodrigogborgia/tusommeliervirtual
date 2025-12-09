from heygen_client import open_session, speak_text
from config import AVATAR_ID, VOICE_ID, LANGUAGE
import logging

logger = logging.getLogger("sommelier")

def start_avatar_session():
    """
    Abre una sesión de avatar en HeyGen y devuelve tanto el session_id como el token.
    """
    session = open_session(AVATAR_ID, interactive=True)
    session_id = session.get("session_id")
    token = session.get("token")

    logger.info(f"Avatar session started. session_id={session_id}, token={token}")

    return {
        "session_id": session_id,
        "token": token
    }

def say(session_id: str, text: str):
    """
    Envía texto al avatar para que lo hable, usando la sesión activa.
    """
    return speak_text(
        session_id=session_id,
        text=text,
        voice_id=VOICE_ID,
        language=LANGUAGE
    )
