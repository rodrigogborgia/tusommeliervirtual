import os
import requests
import logging
import random
import re
import time
import unicodedata
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from dotenv import load_dotenv
from langdetect import detect
from sklearn.metrics.pairwise import cosine_similarity
from pydantic import BaseModel
import threading
import numpy as np
import openai
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from orchestrator import say

class SpeakRequest(BaseModel):
    session_id: str
    text: str

load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sommelier")

# --- Variables de entorno ---
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
AVATAR_ID = os.getenv("AVATAR_ID")
VOICE_ID = os.getenv("VOICE_ID")
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
openai.api_key = OPENAI_API_KEY

# --- Inicializar ChromaDB ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

chroma_client = chromadb.PersistentClient(
    path=os.path.join(BASE_DIR, "backend", "chroma"),
    settings=Settings(anonymized_telemetry=False)
)

# Intentar obtener la colección, crearla si no existe
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "pdf_knowledge")
try:
    collection = chroma_client.get_collection(COLLECTION_NAME)
except Exception:
    collection = chroma_client.create_collection(COLLECTION_NAME)

embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# --- FastAPI ---
app = FastAPI()

# --- Cache simple ---
class SimpleCache:
    def __init__(self, ttl_seconds: int = 300, max_items: int = 256):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self.store: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def _prune(self):
        now = time.time()
        keys_to_delete = [k for k, v in self.store.items() if now - v["time"] > self.ttl]
        for k in keys_to_delete:
            del self.store[k]
        if len(self.store) > self.max_items:
            sorted_items = sorted(self.store.items(), key=lambda kv: kv[1]["time"])
            for k, _ in sorted_items[:len(self.store) - self.max_items]:
                del self.store[k]

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            self._prune()
            item = self.store.get(key)
        if not item:
            return None
        if time.time() - item["time"] > self.ttl:
            with self.lock:
                if key in self.store:
                    del self.store[key]
            return None
        return item["value"]

    def set(self, key: str, value: Any):
        with self.lock:
            self._prune()
            self.store[key] = {"value": value, "time": time.time()}

cache = SimpleCache(ttl_seconds=300, max_items=256)

# --- Helpers de texto y utilidades ---
def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)

def clean_text(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("\n", " ").replace("\f", " ")
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text)
    text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)
    return text.strip()

# --- Helpers LLM ---
def call_llm(prompt: str) -> str:
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY no configurada")
        return "Error: falta la API key de OpenAI."

    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Eres un asistente experto que responde de forma clara y natural."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        answer = response["choices"][0]["message"]["content"].strip()
        return answer
    except Exception as e:
        logger.error(f"Error llamando al LLM: {e}")
        return "Error: no se pudo generar respuesta con el LLM."

# --- Endpoints básicos ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import logging
from orchestrator import open_session
from config import AVATAR_ID, VOICE_ID, LANGUAGE

logger = logging.getLogger("sommelier")

router = APIRouter()

@app.post("/api/session/start")
def start_session():
    if not HEYGEN_API_KEY:
        return JSONResponse(
            {"error": "missing_api_key", "details": "HEYGEN_API_KEY no configurado"},
            status_code=500
        )

    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {
        "Authorization": f"Bearer {HEYGEN_API_KEY}",
        "accept": "application/json"
    }

    try:
        r = requests.post(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        token = data.get("token")
    except Exception as e:
        return JSONResponse(
            {"error": "heygen_create_token_failed", "details": str(e)},
            status_code=502
        )

    logger.info(f"Token creado: {token}")

    return JSONResponse({
        "token": token,
        "avatar_id": AVATAR_ID,
        "voice_id": VOICE_ID,
        "language": LANGUAGE
    })

sessions = {}

@app.post("/api/session/register")
def register_session(req: dict):
    """
    El frontend debe llamar a este endpoint justo después de createStartAvatar,
    enviando { "session_id": ..., "access_token": ... }.
    """
    sid = req.get("session_id")
    token = req.get("access_token")
    if sid and token:
        sessions[sid] = token
        return {"status": "ok"}
    return {"status": "error", "details": "faltan datos"}

@app.post("/api/ask")
def ask(q: str = Query(...), n: int = Query(3)):
    start = time.time()
    cache_key = f"ask:{q}:{n}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # 1. Buscar en Chroma
    query_embedding = embedder([q])
    results = collection.query(query_embeddings=query_embedding, n_results=n)

    docs = results["documents"][0]
    sources = results["metadatas"][0]

    # 2. Armar prompt para el LLM
    llm_prompt = f"""
    Pregunta del usuario: {q}

    Documentos encontrados:
    {docs}

    Por favor:
    - Evalúa si estos documentos son relevantes.
    - Si lo son, sintetiza una respuesta clara y natural.
    - Si no lo son, explica que no encontraste información exacta pero da contexto general.
    """

    # 3. Llamar al LLM con el helper
    answer = call_llm(llm_prompt)

    # 4. Armar payload
    payload = {
        "answer": answer,
        "meta": {
            "sources": sources,
            "confidence_avg": None  # opcional, lo dejamos como placeholder
        },
        "details": "Respuesta generada por LLM"
    }

    # 5. Cachear y devolver
    cache.set(cache_key, payload)
    logger.info(f"/api/ask completed in {time.time() - start:.2f}s")
    return payload

@app.post("/api/speak")
def speak(req: SpeakRequest):
    if not req.session_id or not req.text:
        return JSONResponse(
            {"error": "invalid_request", "details": "Faltan 'session_id' o 'text' en el body"},
            status_code=400
        )

    # Recuperar el access_token asociado a la sesión
    access_token = sessions.get(req.session_id)
    if not access_token:
        return JSONResponse(
            {"error": "invalid_session", "details": "No se encontró access_token para esa sesión"},
            status_code=400
        )

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
        return JSONResponse({"status": "ok", "data": result})
    except Exception as e:
        logger.error(f"heygen speak failed: {e}")
        return JSONResponse(
            {"error": "heygen_speak_failed", "details": str(e)},
            status_code=500
        )

@app.get("/api/routes")
def list_routes():
    return [{"path": route.path, "methods": list(route.methods)} for route in app.router.routes if isinstance(route, APIRoute)]

# --- Servir frontend ---
if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    logger.warning(f"Frontend dist dir not found: {FRONTEND_DIST_DIR}")
