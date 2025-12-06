import os
import requests
import logging
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

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
LANGUAGE = os.getenv("LANGUAGE", "Spanish")

app = FastAPI()

# --- Middleware para loggear requests/responses ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code} {request.method} {request.url}")
    return response

# --- Handler global de excepciones ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Ocurrió un error inesperado.",
            "path": str(request.url),
        },
    )

# --- Ajuste para frontend al mismo nivel que backend ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# --- Inicializar cliente ChromaDB y modelo ---
chroma_client = chromadb.PersistentClient(
    path=os.path.join(BASE_DIR, "backend", "chroma"),
    settings=Settings(anonymized_telemetry=False)
)
collection = chroma_client.get_collection("pdf_knowledge")

# Usar el modelo liviano (384 dims)
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# --- Endpoints del backend bajo prefijo /api ---
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/session/start")
def start_session():
    url = "https://api.heygen.com/v1/streaming.create_token"
    headers = {
        "x-api-key": HEYGEN_API_KEY,
        "accept": "application/json",
        "content-type": "application/json"
    }
    payload = {
        "avatarName": DEXTER_AVATAR_ID,
        "voiceId": VOICE_ID,
        "language": LANGUAGE,
        "quality": "high",
        "video": True
    }

    logger.info(f"Payload enviado a HeyGen: {payload}")

    r = requests.post(url, headers=headers, json=payload)
    logger.info(f"Response status: {r.status_code}")
    logger.info(f"Response text: {r.text}")

    if r.status_code == 200:
        data = r.json().get("data", {})
        return JSONResponse({
            "data": data,
            "avatar_id": DEXTER_AVATAR_ID,
            "voice_id": VOICE_ID,
            "language": LANGUAGE
        })
    else:
        return JSONResponse({"error": r.text}, status_code=r.status_code)

@app.get("/api/stt/transcribe_file")
def transcribe_file(file_path: str = Query(..., description="Ruta del archivo de audio RAW")):
    # TODO: integrar con Vosk WebSocket o cliente local
    return {"file_path": file_path, "transcription": "Transcripción simulada"}

@app.get("/api/search")
def search(q: str = Query(...), n: int = Query(3)):
    logger.info(f"/api/search q='{q}' n={n}")

    # Generar embedding de la consulta
    query_embedding = embedder([q])

    # Buscar en la colección
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n
    )

    # Formatear resultados
    formatted = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        formatted.append({
            "source": meta.get("source", "unknown"),
            "text": doc
        })

    logger.info(f"/api/search returned {len(formatted)} results")
    return {"results": formatted}

from fastapi.routing import APIRoute

@app.get("/api/routes")
def list_routes():
    return [
        {"path": route.path, "methods": list(route.methods)}
        for route in app.router.routes
        if isinstance(route, APIRoute)
    ]

# 👉 Servir el build de Vite en la raíz (al final)
app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
