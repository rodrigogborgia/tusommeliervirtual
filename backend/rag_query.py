import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_COLLECTION

# Cliente persistente apuntando a tu carpeta chroma
client = chromadb.PersistentClient(path="/opt/tusommeliervirtual.com/backend/chroma")

# Colección existente
collection = client.get_collection(CHROMA_COLLECTION)

# Usar el modelo liviano (384 dims)
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

def search(query: str, k: int = 5):
    # Generar embeddings directamente
    q_emb = embedder([query])  # devuelve lista de embeddings
    res = collection.query(query_embeddings=q_emb, n_results=k)
    docs = res["documents"][0]
    ids = res["ids"][0]
    scores = res["distances"][0]
    return [{"id": i, "text": d, "score": s} for i, d, s in zip(ids, docs, scores)]

if __name__ == "__main__":
    results = search("sommelier de carne", k=3)
    for r in results:
        print(f"→ {r['id']} | score={r['score']:.4f}\n{r['text']}\n")
