import os

# HeyGen
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
DEXTER_AVATAR_ID = os.getenv("DEXTER_AVATAR_ID", "")  # ID real del avatar Dexter_Lawyer_Sitting_public
VOICE_ID = os.getenv("VOICE_ID", "1a32e06dde934e69ba2a98a71675dc16")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

# STT (Vosk WebSocket)
STT_WS_URL = os.getenv("STT_WS_URL", "ws://127.0.0.1:2700")
STT_SAMPLE_RATE = int(os.getenv("STT_SAMPLE_RATE", "16000"))

# ChromaDB
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "pdf_knowledge")

# New Relic
NEW_RELIC_ENABLED = os.getenv("NEW_RELIC_ENABLED", "false").lower() in ("1","true","yes")
