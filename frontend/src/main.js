import StreamingAvatar, { StreamingEvents } from "@heygen/streaming-avatar";

console.log("Eventos disponibles en esta versión:", StreamingEvents);

const videoElement = document.getElementById("avatarVideo");
const startButton = document.getElementById("startButton");

let avatar = null;
let sessionId = null;
let avatarReady = false;

startButton.addEventListener("click", async () => {
  console.log("=== Iniciando avatar ===");

  // 1. Pedir token y parámetros al backend
  const resp = await fetch("/api/session/start", { method: "POST" });
  const json = await resp.json();

  const token = json.token;
  const avatar_id = json.avatar_id;
  const voice_id = json.voice_id;
  const language = json.language;

  console.log("=== Datos recibidos del backend ===");
  console.log("Token:", token);
  console.log("Avatar ID:", avatar_id);
  console.log("Voice ID:", voice_id);
  console.log("Language:", language);

  if (!token) {
    console.error("No se recibió token desde el backend. Abortando.");
    return;
  }

  // 2. Crear instancia de avatar
  avatar = new StreamingAvatar({ token });
  console.log("Instancia de avatar creada");

  // 3. Listeners ordenados

// STREAM_READY → conecta video/audio y marca avatarReady
avatar.on(StreamingEvents.STREAM_READY, (event) => {
  console.log("=== STREAM_READY ===", event);
  if (event.detail && videoElement) {
    videoElement.srcObject = event.detail;
    videoElement.volume = 1.0;
    videoElement.onloadedmetadata = () => {
      videoElement.play().catch(console.error);
    };
    console.log("Video + audio conectados al avatar");
  }
  avatarReady = true; // ⚡ marcar que ya está listo para hablar
});

// TRANSCRIPTION → texto reconocido
avatar.on(StreamingEvents.TRANSCRIPTION, (event) => {
  console.log("=== TRANSCRIPTION ===", event);
});

// 👉 NUEVOS listeners de habla del avatar
avatar.on(StreamingEvents.AVATAR_START_TALKING, (event) => {
  console.log("=== AVATAR_START_TALKING ===", event);
});

avatar.on(StreamingEvents.AVATAR_TALKING_MESSAGE, (event) => {
  console.log("=== AVATAR_TALKING_MESSAGE ===", event);
});

avatar.on(StreamingEvents.AVATAR_STOP_TALKING, (event) => {
  console.log("=== AVATAR_STOP_TALKING ===", event);
});

avatar.on(StreamingEvents.AVATAR_END_MESSAGE, (event) => {
  console.log("=== AVATAR_END_MESSAGE ===", event);
});

  // Listener genérico para depuración
  Object.values(StreamingEvents).forEach((ev) => {
    avatar.on(ev, (event) => {
      console.log("EVENT:", ev, event);
    });
  });

  // 4. Iniciar avatar con parámetros y capturar sessionInfo
  const sessionInfo = await avatar.createStartAvatar({
    avatarName: avatar_id,
    voiceId: voice_id,
    language: language,
    quality: "high",
    video: true,
    gentMode: false
  });

  // Loguear y extraer session_id si viene en la respuesta
  console.log("createStartAvatar returned:", JSON.stringify(sessionInfo, null, 2));
  if (sessionInfo && sessionInfo.session_id) {
    sessionId = sessionInfo.session_id;
    console.log("Session ID (from createStartAvatar):", sessionId);

    // ⚡ NUEVO: enviar session_id + access_token al backend
    await fetch("/api/session/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionInfo.session_id,
        access_token: sessionInfo.access_token,
      }),
    });
    console.log("Session registrada en backend con access_token");
  } else {
    console.warn("createStartAvatar no devolvió session_id. sessionInfo:", sessionInfo);
  }
});

// 2) Consulta semántica con /api/ask + hablar resultado
document.addEventListener("DOMContentLoaded", () => {
  const searchButton = document.getElementById("searchButton");
  const searchInput = document.getElementById("searchInput");
  const searchResults = document.getElementById("searchResults");

  searchButton.addEventListener("click", async () => {
    const query = searchInput.value.trim();
    if (!query) return;

    try {
      // 1. Pedir respuesta al backend/LLM
      const res = await fetch(`/api/ask?q=${encodeURIComponent(query)}&n=3`, { method: "POST" });
      const data = await res.json();

      // 2. Mostrar respuesta en pantalla
      searchResults.innerHTML = "";
      if (data.answer) {
        searchResults.innerHTML = `<p>${data.answer}</p>`;
        console.log("Respuesta del LLM:", data.answer);

        // 3. Enviar respuesta al avatar SOLO si está listo
        if (avatar && avatarReady) {
          await avatar.speak({
            text: data.answer,
            task_type: "REPEAT"   // ⚡ fuerza modo repetir, no modo agente
          });
          console.log("Texto enviado al avatar via SDK (REPEAT):", data.answer);
        } else {
          console.warn("Avatar aún no está listo para hablar");
        }
      } else {
        searchResults.textContent = "No se encontraron resultados.";
      }
    } catch (err) {
      console.error("Error en búsqueda:", err);
      searchResults.textContent = "Error en la consulta.";
    }
  });
});
