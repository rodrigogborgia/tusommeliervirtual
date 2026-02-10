# End-of-speech / tolerancia al silencio — investigación

## Problema
Si el usuario habla **pausado**, el sistema a veces toma **solo parte de la frase** y el avatar empieza a hablar antes de que termine. Parece que falta tunear la **tolerancia de silencio** antes de considerar "fin de habla".

---

## 1. LiveKit / Silero VAD (referencia técnica)

El ecosistema **LiveKit Agents** (relacionado con el stack de voz) usa el plugin **Silero VAD** con estos parámetros relevantes:

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| **`min_silence_duration`** | **0.55 s** | Al final de cada habla, **cuántos segundos de silencio** esperar antes de dar por terminado el turno ("end of speech"). |
| `min_speech_duration` | 0.05 s | Duración mínima de habla para iniciar un chunk. |
| `prefix_padding_duration` | 0.5 s | Padding al inicio de cada chunk de habla. |

- Documentación: https://docs.livekit.io/agents/logic-structure/turns/vad/
- Referencia Python: https://docs.livekit.io/reference/python/livekit/plugins/silero/index.html  

**Conclusión:** El concepto que buscamos es **min_silence_duration** (en segundos). Un valor más alto = más tolerancia a pausas antes de cortar la frase.

---

## 2. Live Avatar (HeyGen) — qué dice la documentación

- **STT en FULL mode:** el FAQ indica que el ASR lo hacen **Deepgram** y **AssemblyAI** (server-side).  
  https://help.heygen.com/en/articles/12758866-liveavatar-faq
- En la **API pública** de Live Avatar (`POST /v1/sessions/token`) **no** aparece documentado ningún parámetro tipo:
  - `end_of_speech_timeout_ms`
  - `min_silence_duration`
  - `silence_timeout`
  - `utterance_end_ms`
- **Discusiones en docs.liveavatar.com:** no hay un hilo específico sobre "end of speech" o "silence timeout". Hay temas de STT (idiomas), errores 500, latencia, etc., pero ninguno que documente un parámetro de tolerancia al silencio.

---

## 3. GitHub / LiveKit Agents

- **Issue #326** (livekit/agents): explica que el evento **END_OF_SPEECH** puede emitirse **después** de **FINAL_TRANSCRIPT** (por el tiempo de inferencia y llamada al STT), lo que afecta el timing que ve el cliente.  
  https://github.com/livekit/agents/issues/326

---

## 4. Qué hicimos en este repo

- Añadimos soporte opcional para **`LIVEAVATAR_END_OF_SPEECH_MS`** en el backend y enviamos **`end_of_speech_timeout_ms`** en `avatar_persona` al crear el token.
- Si la API de Live Avatar **acepta** ese campo (o uno con nombre parecido), debería aumentar la tolerancia al silencio.
- Si **no** lo acepta, el backend ignora el error o el campo es ignorado por el servidor; no rompe nada.

---

## 5. Recomendaciones

1. **Probar en producción** con algo como:
   ```bash
   LIVEAVATAR_END_OF_SPEECH_MS=1200
   ```
   o `1500` / `2000` (ms). Si la API lo usa, deberías notar menos cortes al hablar pausado.

2. **Preguntar a Live Avatar / HeyGen** en su foro o soporte, por ejemplo:
   - **Foro:** https://docs.liveavatar.com/discuss  
   - Pregunta sugerida:  
     *"In FULL mode, when the user speaks with pauses, the avatar sometimes responds after the first phrase fragment (partial transcription). Is there a way to increase the silence timeout or end-of-speech delay so the system waits longer before considering the user finished speaking? For example, a parameter like min_silence_duration (seconds) or end_of_speech_timeout_ms in the session token or avatar_persona. We use the Create Session Token API."*

3. **Referencia al ecosistema LiveKit:** si en algún momento te confirman que usan algo tipo Silero VAD o parámetros similares, el nombre más probable es **min_silence_duration** (en segundos); nuestro `end_of_speech_timeout_ms` sería el mismo concepto en milisegundos.

---

## 6. Enlaces útiles

- Live Avatar – Create Session Token: https://docs.liveavatar.com/reference/create_session_token_v1_sessions_token_post  
- Live Avatar – Full mode config: https://docs.liveavatar.com/docs/full-mode-configurations  
- Live Avatar – Discussions: https://docs.liveavatar.com/discuss  
- LiveKit – Silero VAD: https://docs.livekit.io/agents/logic-structure/turns/vad/  
- LiveKit agents #326 (END_OF_SPEECH vs FINAL_TRANSCRIPT): https://github.com/livekit/agents/issues/326  
- Live Avatar FAQ (STT = Deepgram/AssemblyAI): https://help.heygen.com/en/articles/12758866-liveavatar-faq  
