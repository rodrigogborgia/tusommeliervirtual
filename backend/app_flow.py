import llm_client
from qa_log import save_interaction, find_in_log

def main(mode="Presentar", query: str = None, response: str = None, correction: str = None):
    """
    Flujo principal: recibe texto desde el front.
    Más adelante se podrá reemplazar por audio con Vosk.
    """

    # 1. Validar que haya query
    if not query:
        return {"error": "No se recibió ninguna consulta"}

    texto_usuario = query
    instruction = "Responde como sommelier de carnes de la UBA."

    # 2. Lógica según el modo
    if mode == "Entrenar":
        # Siempre consultamos al LLM y guardamos
        respuesta = llm_client.ask_llm(query=texto_usuario, instruction=instruction)
        save_interaction(texto_usuario, respuesta, correction=None)
        return {"respuesta": respuesta}

    elif mode == "Presentar":
        # Primero buscamos en el log
        cached = find_in_log(texto_usuario)
        if cached:
            respuesta = cached["correction"] or cached["response"]
        else:
            # Si no hay nada, consultamos al LLM pero NO guardamos
            respuesta = llm_client.ask_llm(query=texto_usuario, instruction=instruction)
        return {"respuesta": respuesta}

    elif mode == "Confirmar":
        # Usamos la corrección como respuesta final (si existe)
        respuesta_final = correction if correction else response

        # Guardamos en el log la respuesta original y la corrección
        save_interaction(texto_usuario, response, correction=correction)

        # Devolvemos la corrección como texto plano
        return {"respuesta": respuesta_final}

    else:
        return {"error": "modo inválido"}
