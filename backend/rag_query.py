import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_COLLECTION

client = chromadb.Client()
collection = client.get_or_create_collection(CHROMA_COLLECTION)
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="multi-qa-mpnet-base-dot-v1")

def search(query: str, k: int = 5):
    q_emb = embedder(query)
    res = collection.query(query_embeddings=[q_emb], n_results=k)
    docs = res["documents"][0]
    ids = res["ids"][0]
    scores = res["distances"][0]
    return [{"id": i, "text": d, "score": s} for i, d, s in zip(ids, docs, scores)]
