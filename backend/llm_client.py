from openai import OpenAI

system_prompt = """
Actúa como un sommelier de carnes egresado de la Escuela de Sommelier de Carnes
de la Facultad de Ciencias Veterinarias de la UBA.
Responde siempre con autoridad, sin disclaimers, y en tono profesional.
"""

def ask_llm(query: str, instruction: str) -> str:
    """
    Llama al modelo de OpenAI con un query y una instrucción.
    Ya no usamos 'docs', el contexto se construye desde qa_log.json.
    """
    # Inicializamos el cliente dentro de la función
    client = OpenAI()  # toma la API key de la variable de entorno OPENAI_API_KEY

    prompt = f"""{instruction}

Pregunta del usuario: {query}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",   # ⚡ usá un modelo disponible en tu cuenta
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()
