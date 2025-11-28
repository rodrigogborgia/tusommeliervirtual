from orchestrator import start_avatar_session, say
from rag_query import search
from stt_client import transcribe_file  # tu módulo que usa websockets.connect

def main():
    # 1. Arrancar sesión con el avatar
    session_id = start_avatar_session()

    # 2. Transcribir un audio local (ejemplo)
    texto_usuario = transcribe_file("test_audio.wav")
    print("Texto reconocido:", texto_usuario)

    # 3. Buscar contexto en PDFs con RAG
    resultados = search(texto_usuario, k=3)
    if resultados:
        contexto = resultados[0]["text"]  # tomamos el fragmento más relevante
        print("Fragmento encontrado:", contexto)
    else:
        contexto = "No encontré información en los documentos."

    # 4. Generar respuesta final
    respuesta = f"Me preguntaste: '{texto_usuario}'. Según el documento: {contexto}"

    # 5. Pasar la respuesta al avatar
    output = say(session_id, respuesta)
    print("Respuesta del avatar:", output)

if __name__ == "__main__":
    main()
