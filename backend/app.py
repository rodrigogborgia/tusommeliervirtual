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
import numpy as np

# --- Nuevos imports para ChromaDB ---
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

load_dotenv()

# --- Configuración de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sommelier")

# --- Variables de entorno ---
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
DEXTER_AVATAR_ID = os.getenv("DEXTER_AVATAR_ID")
VOICE_ID = os.getenv("VOICE_ID")
DEFAULT_LANGUAGE = os.getenv("LANGUAGE", "Spanish")

# --- Frases de apertura variadas ---
opening_phrases = [
    "Lo que yo sé es que",
    "Los manuales indican lo siguiente",
    "Un documento técnico explica que",
    "Buscando en mi memoria, aparece esto",
    "Lo que sé sobre carnes es que",
    "Entre mis referencias encontré que",
    "Un texto especializado dice",
    "Mis registros mencionan que"
]

# --- Frases de fallback variadas ---
fallback_phrases = [
    "¡Qué buena pregunta! ¿Podés darme más detalles para buscar en mis manuales de carnes?",
    "Interesante tema, pero necesito que lo aclares un poco más.",
    "No lo encontré en mis referencias, ¿querés reformular la consulta?",
    "Me encantaría ayudarte, ¿podés precisar mejor tu duda?",
    "No tengo referencias sobre ese tema en mis manuales, pero puedo ayudarte con cortes de carne."
]

# --- Normalización de texto ---
def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # ⚠️ No eliminar guiones legítimos aquí, se maneja en clean_text
    return text

# --- Limpieza avanzada ---
def clean_text(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("\n", " ").replace("\f", " ")
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text)  # elimina duplicaciones consecutivas
    text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)  # une palabras cortadas por guión
    text = re.sub(r"\b\d+\b", "", text)
    return text.strip()

# --- Filtro semántico más estricto ---
def is_relevant(text: str, query: str) -> bool:
    normalized_text = unicodedata.normalize("NFKC", text.lower())
    query_words = [unicodedata.normalize("NFKC", w.lower()) for w in query.split() if len(w) > 3]
    return all(word in normalized_text for word in query_words)

# --- Detección de idioma robusta ---
def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        if lang.startswith("pt") and any(word in text.lower() for word in ["carne", "jugoso", "animal", "vino"]):
            return "Spanish (forced)"
        if lang.startswith("es"):
            return "Spanish"
        elif lang.startswith("pt"):
            return "Portuguese"
        else:
            return "English"
    except:
        return DEFAULT_LANGUAGE

# --- Longitud dinámica ---
def dynamic_word_limit(query: str, base: int = 40, max_len: int = 70) -> int:
    q_len = len(query.split())
    if q_len >= 10:
        return max_len
    if 5 <= q_len < 10:
        return int((base + max_len) / 2)
    return base

# --- Paráfrasis sommelier ---
def paraphrase_sommelier(text: str) -> str:
    text = re.sub(r"\bcojeras\b", "problemas de locomoción", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhematomas\b", "marcas en la canal", text, flags=re.IGNORECASE)
    text = re.sub(r"\binoc(u|o)idad\b", "seguridad alimentaria", text, flags=re.IGNORECASE)
    text = re.sub(r"Un documento técnico explica que\s*:?\s*", "", text)
    return text.strip()

# --- Confidence con embeddings ---
def confidence_with_embeddings(text: str, query: str) -> float:
    try:
# ⚠️ Cachear embeddings de documentos para performance
        q_emb = embedder([query])[0]
        if hasattr(text, "_cached_emb"):
            t_emb = text._cached_emb
        else:
            t_emb = embedder([text])[0]
        sim = cosine_similarity([q_emb], [t_emb])[0][0]
        return round(float(sim), 2)

    except Exception as e:
        logger.warning(f"Confidence embedding failed: {e}")
        return confidence_by_overlap(text, query)  # fallback al método anterior

# --- Confidence por coincidencias ---
def confidence_by_overlap(text: str, query: str) -> float:
    query_words = query.lower().split()
    if not query_words:
        return 0.0
    matches = sum(1 for w in query_words if w in text.lower())
    return round(matches / len(query_words), 2)

# --- Fallback narrativo contextual ---
def contextual_fallback(query: str) -> str:
    q = query.lower()
    if "vino" in q:
        return "No encontré referencias sobre vinos en mis manuales, pero puedo recomendarte cortes de carne para acompañar."
    if "corte" in q or "jugoso" in q:
        return "No encontré referencias sobre cortes jugosos, pero puedo ayudarte con otros cortes."
    if "bienestar" in q or "animal" in q:
        return "No encontré referencias específicas, pero puedo contarte sobre prácticas de bienestar animal en la industria."
    return "No encontré referencias exactas, pero puedo orientarte con información general de mis manuales."

# --- Multi‑fragmento narrativo ---
def compose_multi_fragment(docs: List[str], query: str, max_words: int) -> str:
    connectors = ["Primero", "Además", "Finalmente"]
    used_openings = set()
    parts = []
    for i, doc in enumerate(docs):
        cleaned = clean_text(doc)
        if not is_relevant(cleaned, query):
            continue
        paraphrased = paraphrase_sommelier(cleaned)
        opening = random.choice([o for o in opening_phrases if o not in used_openings] or opening_phrases)
        used_openings.add(opening)
        connector = connectors[i % len(connectors)]
        snippet = " ".join(paraphrased.split()[:max_words // max(1, len(docs))])
        parts.append(f"{connector}, {opening.lower()}: {snippet}")
    composed = " ".join(parts)
    return composed.strip()

# --- Cache simple ---
import threading

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
            del self.store[key]
            return None
        return item["value"]

    def set(self, key: str, value: Any):
        self._prune()
        self.store[key] = {"value": value, "time": time.time()}

cache = SimpleCache(ttl_seconds=300, max_items=256)

app = FastAPI()

# --- Middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    elapsed = round(time.time() - start, 2)
    logger.info(f"Response: {response.status_code} {request.method} {request.url} | elapsed={elapsed}s")
    return response

# --- Handler global ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Ocurrió un error inesperado en el backend. Probá nuevamente en unos segundos.",
            "path": str(request.url),
        },
    )

# --- Ajuste frontend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# --- Inicializar ChromaDB ---
chroma_client = chromadb.PersistentClient(
    path=os.path.join(BASE_DIR, "backend", "chroma"),
    settings=Settings(anonymized_telemetry=False)
)
collection = chroma_client.get_collection("pdf_knowledge")
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# --- Endpoints ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/session/start")
def start_session():
    if not HEYGEN_API_KEY:
        return JSONResponse(
            {"error": "missing_api_key", "details": "HEYGEN_API_KEY no configurado"},
            status_code=500
        )

    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {
        "x-api-key": HEYGEN_API_KEY,
        "accept": "application/json",
        "content-type": "application/json"
    }
    payload = {
        "avatarName": DEXTER_AVATAR_ID,
        "voiceId": VOICE_ID,
        "language": DEFAULT_LANGUAGE,
        "quality": "high",
        "video": True
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        return JSONResponse(
            {"error": "no_se_pudo_iniciar_sesion_heygen", "details": str(e)},
            status_code=502
        )

    if r.status_code == 200:
        data = r.json().get("data", {})
        return JSONResponse({
            "data": data,
            "avatar_id": DEXTER_AVATAR_ID,
            "voice_id": VOICE_ID,
            "language": DEFAULT_LANGUAGE
        })
    else:
        return JSONResponse(
            {"error": "heygen_create_token_failed", "details": r.text},
            status_code=r.status_code
        )

def search(q: str = Query(...), n: int = Query(3)):
    start = time.time()
    cache_key = f"search:{q}:{n}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Embedding de la query
    query_embedding = embedder([q])
    results = collection.query(query_embeddings=query_embedding, n_results=n)

    # --- Fallback narrativo si no hay documentos ---
    if not results["documents"] or not results["documents"][0]:
        fb = contextual_fallback(q)
        payload = {
            "results": [
                {"source": "none", "text": fb, "page": None, "confidence": None}
            ],
            "summary": f"Primero, lo que sé es que: {fb}"
        }
        cache.set(cache_key, payload)
        return payload

    # --- Filtro semántico más estricto ---
    formatted = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        if is_relevant(doc, q):  # exige que todas las palabras clave estén presentes
            cleaned = clean_text(doc)
            paraphrased = paraphrase_sommelier(cleaned)
            conf = confidence_with_embeddings(paraphrased, q)
            formatted.append({
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", None),
                "confidence": conf,
                "text": paraphrased
            })

    # --- Fallback narrativo si todo fue descartado ---
    if not formatted:
        fb = contextual_fallback(q)
        payload = {
            "results": [
                {"source": "none", "text": fb, "page": None, "confidence": None}
            ],
            "summary": f"Primero, lo que sé es que: {fb}"
        }
        cache.set(cache_key, payload)
        return payload

    # --- Armar summary narrativo con conectores ---
    summary_parts = []
    if len(formatted) >= 1:
        opening = random.choice(opening_phrases)
        summary_parts.append(f"Primero, mis registros mencionan que: {formatted[0]['text']}")
    if len(formatted) >= 2:
        summary_parts.append(f"Además, un texto especializado dice: {formatted[1]['text']}")
    if len(formatted) >= 3:
        summary_parts.append(f"Finalmente, lo que sé sobre carnes es que: {formatted[2]['text']}")

    payload = {
        "results": formatted,
        "summary": " ".join(summary_parts)
    }

    cache.set(cache_key, payload)
    logger.info(f"/api/search completed in {time.time() - start:.2f}s")
    return payload

@app.post("/api/ask")
def ask(q: str = Query(...), n: int = Query(3)):
    start = time.time()
    cache_key = f"ask:{q}:{n}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    query_embedding = embedder([q])
    results = collection.query(query_embeddings=query_embedding, n_results=n)

    # --- Filtro semántico más estricto ---
    relevant_docs = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        if is_relevant(doc, q):  # exige que todas las palabras clave estén presentes
            cleaned = clean_text(doc)
            paraphrased = paraphrase_sommelier(cleaned)
            relevant_docs.append(paraphrased)

    # --- Fallback narrativo si no hay docs relevantes ---
    if not relevant_docs:
        fb = contextual_fallback(q)
        answer = fb
        meta_block = {"sources": [], "confidence_avg": None}
        payload = {
            "answer": answer,
            "meta": meta_block,
            "language": detect_language(answer),
            "error": "heygen_no_disponible",
            "details": "El avatar no pudo hablar en este momento, pero tu respuesta está lista en texto."
        }
        cache.set(cache_key, payload)
        return payload

    # --- Confidence con embeddings ---
    confidences = [confidence_with_embeddings(clean_text(d), q) for d in relevant_docs]
    confidence_avg = round(sum(confidences) / len(confidences), 2) if confidences else None

    # --- Armar narrativa multi‑fragmento ---
    answer_parts = []
    if len(relevant_docs) >= 1:
        answer_parts.append(f"Primero, lo que sé sobre carnes es que: {relevant_docs[0]}")
    if len(relevant_docs) >= 2:
        answer_parts.append(f"Además, buscando en mi memoria, aparece esto: {relevant_docs[1]}")
    if len(relevant_docs) >= 3:
        answer_parts.append(f"Finalmente, un documento técnico explica que: {relevant_docs[2]}")

    answer = " ".join(answer_parts)

    used_sources = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        if is_relevant(doc, q):
            used_sources.append(meta)

    meta_block = {
        "sources": used_sources,
        "confidence_avg": confidence_avg
    }

    payload = {
        "answer": answer,
        "meta": meta_block,
        "language": detect_language(answer),
        "error": "heygen_no_disponible",
        "details": "El avatar no pudo hablar en este momento, pero tu respuesta está lista en texto."
    }

    cache.set(cache_key, payload)
    logger.info(f"/api/ask completed in {time.time() - start:.2f}s")
    return payload

@app.get("/api/routes")
def list_routes():
    return [
        {"path": route.path, "methods": list(route.methods)}
        for route in app.router.routes
        if isinstance(route, APIRoute)
    ]

# 👉 Servir el build del frontend
if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    logger.warning(f"Frontend dist dir not found: {FRONTEND_DIST_DIR}")
