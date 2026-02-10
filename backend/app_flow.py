import logging
from . import llm_client
from qa_log import QALog

logger = logging.getLogger("app-flow")
qa_logger = QALog()

def main(mode="Presentar", query: str = None, response: str = None, correction: str = None, skip_save: bool = False):
    """
    Flujo principal: recibe texto desde el front.
    """

    # 1. Validar que haya query
    if not query:
        return {"error": "No se recibió ninguna consulta"}

    texto_usuario = query
    instruction = "Responde como sommelier de carnes de la UBA."

    # Marca inicio de interacción
    qa_logger.mark("interaction_start")
    logger.info(f"FLOW_INPUT (mode={mode}): {texto_usuario}")

    try:
        # 2. Lógica según el modo
        if mode == "Entrenar":
            qa_logger.mark("llm_start")
            respuesta = llm_client.ask_llm(query=texto_usuario, instruction=instruction)
            qa_logger.mark("llm_done")
            qa_logger.diff("llm_start", "llm_done")

            # 🔊 Generación de voz/avatar
            qa_logger.mark("avatar_start")
            # aquí deberías invocar el motor de voz/avatar con `respuesta`
            qa_logger.mark("avatar_done")
            qa_logger.diff("avatar_start", "avatar_done")

            qa_logger.save_interaction(query=texto_usuario, response=respuesta, correction=None)
            logger.info(f"FLOW_OUTPUT: {respuesta}")

            qa_logger.mark("interaction_end")
            qa_logger.diff("interaction_start", "interaction_end")

            return {"respuesta": respuesta}

        elif mode == "Presentar":
            llm_time_ms = None
            # Primero buscamos en el log
            cached_entries = qa_logger.find_in_log(query=texto_usuario)
            if cached_entries:
                last_entry = cached_entries[-1]
                respuesta = last_entry.get("correction") or last_entry.get("response")
                llm_time_ms = 0  # cache hit
            else:
                qa_logger.mark("llm_start")
                respuesta = llm_client.ask_llm(query=texto_usuario, instruction=instruction)
                qa_logger.mark("llm_done")
                d = qa_logger.diff("llm_start", "llm_done")
                llm_time_ms = round(d * 1000, 1) if d is not None else None

                if not skip_save:
                    qa_logger.save_interaction(query=texto_usuario, response=respuesta, correction=None)

            logger.info(f"FLOW_OUTPUT: {respuesta}")

            # 🔊 Generación de voz/avatar (backend no la ejecuta; el frontend lo hace)
            qa_logger.mark("avatar_start")
            qa_logger.mark("avatar_done")
            qa_logger.diff("avatar_start", "avatar_done")

            qa_logger.mark("interaction_end")
            qa_logger.diff("interaction_start", "interaction_end")

            return {"respuesta": respuesta, "llm_time_ms": llm_time_ms}

        elif mode == "Confirmar":
            # Usamos la corrección como respuesta final (si existe)
            respuesta_final = correction if correction else response

            qa_logger.save_interaction(query=texto_usuario, response=response, correction=correction)
            logger.info(f"FLOW_OUTPUT (confirm): {respuesta_final}")

            # 🔊 Generación de voz/avatar
            qa_logger.mark("avatar_start")
            # aquí deberías invocar el motor de voz/avatar con `respuesta_final`
            qa_logger.mark("avatar_done")
            qa_logger.diff("avatar_start", "avatar_done")

            qa_logger.mark("confirm_done")
            qa_logger.mark("interaction_end")
            qa_logger.diff("interaction_start", "interaction_end")

            return {"respuesta": respuesta_final}

        else:
            return {"error": "modo inválido"}

    except Exception as e:
        logger.error(f"LLM error: {e}")
        return {"respuesta": "Lo siento, hubo un error procesando tu consulta."}
