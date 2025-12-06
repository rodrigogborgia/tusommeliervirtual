import os
import chromadb
from chromadb.utils import embedding_functions
from pdfminer.high_level import extract_text
from config import CHROMA_COLLECTION

# ✅ Usar persistencia en disco
client = chromadb.PersistentClient(path="./chroma")
collection = client.get_or_create_collection(CHROMA_COLLECTION)

# Embedding function
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name = "all-MiniLM-L6-v2"
)

def chunk_text(s, size=800, overlap=100):
    out, i = [], 0
    while i < len(s):
        out.append(s[i:i+size])
        i += size - overlap
    return out

def ingest_pdf(pdf_path: str, doc_id: str):
    text = extract_text(pdf_path)
    chunks = chunk_text(text)

    # ✅ Aplanar cada embedding
    embeddings = [embedder(c)[0] for c in chunks]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
        metadatas=[{"doc_id": doc_id, "source": os.path.basename(pdf_path)} for _ in chunks]
    )
    return {"doc_id": doc_id, "chunks": len(chunks)}

