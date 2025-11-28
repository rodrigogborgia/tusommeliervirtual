import os, sys, re
from rag_ingest import ingest_pdf
from config import CHROMA_COLLECTION
import chromadb

PDF_DIR = "/opt/tusommeliervirtual.com/backend/pdfs/"

def normalize_name(fname):
    name = os.path.splitext(fname)[0]
    name = name.lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name

def main():
    if not os.path.exists(PDF_DIR):
        print(f"[ERROR] El directorio {PDF_DIR} no existe.", flush=True)
        sys.exit(1)

    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"[INFO] No se encontraron PDFs en {PDF_DIR}.", flush=True)
        return

    client = chromadb.Client()
    collection = client.get_or_create_collection(CHROMA_COLLECTION)

    total = 0
    print(f"[INFO] Ingestado: {total}", flush=True)

    for fname in pdf_files:
        path = os.path.join(PDF_DIR, fname)
        doc_id = normalize_name(fname)
        print(f"[INFO] Procesando: {fname} → doc_id={doc_id}", flush=True)

        try:
            result = ingest_pdf(path, doc_id)
            total += 1
            print(f"[OK] Ingestado: {result}", flush=True)
            print(f"[INFO] Total documentos ahora: {collection.count()}", flush=True)
        except Exception as e:
            print(f"[ERROR] Falló la ingesta de {fname}: {e}", flush=True)

    print(f"[INFO] Ingesta completada. Total documentos procesados: {total}", flush=True)

if __name__ == "__main__":
    main()
