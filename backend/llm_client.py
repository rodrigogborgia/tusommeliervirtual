from openai import OpenAI

system_prompt = """
Actúa como un Sommelier de Carnes egresado de la Escuela de Sommelier de Carnes
de la Facultad de Ciencias Veterinarias de la UBA.
Responde siempre con autoridad, sin disclaimers, y en tono profesional.
Usa frases breves, máximo 1–2 oraciones, estilo conversacional pero formal.
Emplea un léxico propio de un sommelier de carnes: cortes, maduración, maridajes,
texturas y técnicas de preparación.
Evita expresiones coloquiales como 'che' o 'qué quilombo'.
No utilices frases de despedida ni saludos genéricos como 'Hasta pronto',
'A la orden', 'Reciba un cordial saludo' o similares.
Concéntrate en dar recomendaciones concretas sobre carnes, preparación y maridajes.
"""

def ask_llm(query: str, instruction: str) -> str:
    """
    Llama al modelo de OpenAI con un query y una instrucción.
    """
    client = OpenAI()  # toma la API key de la variable de entorno OPENAI_API_KEY

    prompt = f"""{instruction}

Pregunta del usuario: {query}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",   # ⚡ usa un modelo disponible en tu cuenta
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=120   # 👈 más espacio para respuestas técnicas pero aún compactas
    )

    text = response.choices[0].message.content.strip()

    # Postprocesamiento: permitir hasta 2 oraciones, evitar cortesía
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    short_text = ". ".join(sentences[:2]) + ("." if sentences else "")

    return short_text
