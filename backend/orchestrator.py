from heygen_client import open_session, speak_text
from config import DEXTER_AVATAR_ID, VOICE_ID, LANGUAGE

def start_avatar_session():
    session = open_session(DEXTER_AVATAR_ID, interactive=True)
    return session["session_id"]

def say(session_id: str, text: str):
    return speak_text(session_id=session_id, text=text, voice_id=VOICE_ID, language=LANGUAGE)
