import StreamingAvatar, { StreamingEvents } from "@heygen/streaming-avatar";

console.log("Eventos disponibles en esta versión:", StreamingEvents);

const videoElement = document.getElementById("avatarVideo");
const startButton = document.getElementById("startButton");
const searchButton = document.getElementById("searchButton");
const searchInput = document.getElementById("searchInput");
const searchResults = document.getElementById("searchResults");

// NUEVO: botones de modo y banners
const trainButton = document.getElementById("trainButton");
const presentButton = document.getElementById("presentButton");
const modeBanner = document.getElementById("modeBanner");
const statusBanner = document.getElementById("statusBanner");

let avatar = null;
let sessionId = null;
let avatarReady = false;
let currentMode = "Presentar"; // default

// === Gestión de modos ===
trainButton.addEventListener("click", () => {
  currentMode = "Entrenar";
  modeBanner.innerText = "Modo Entrenar";
  modeBanner.style.backgroundColor = "#e74c3c";
});

presentButton.addEventListener("click", () => {
  currentMode = "Presentar";
  modeBanner.innerText = "Modo Presentar";
  modeBanner.style.backgroundColor = "#2ecc71";
});

// === Iniciar avatar ===
startButton.addEventListener("click", async () => {
  console.log("=== Iniciando avatar ===");
  statusBanner.innerText = "Iniciando avatar...";

  try {
    // 1. Pedir token y parámetros al backend
    const resp = await fetch("/api/session/start", { method: "POST" });
    const json = await resp.json();

    const token = json.token;
    const avatar_id = json.avatar_id;
    const voice_id = json.voice_id;
    const language = json.language;

    if (!token) {
      statusBanner.innerText = "Error: no se recibió token ❌";
      console.error("No se recibió token desde el backend. Abortando.");
      return;
    }

    // 2. Crear instancia de avatar
    avatar = new StreamingAvatar({ token });
    console.log("Instancia de avatar creada");

    // 3. Listeners ordenados
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
      avatarReady = true;
      statusBanner.innerText = "Avatar listo para hablar ✅";
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

    if (sessionInfo && sessionInfo.session_id) {
      sessionId = sessionInfo.session_id;
      console.log("Session ID:", sessionId);

      await fetch("/api/session/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionInfo.session_id,
          access_token: sessionInfo.access_token,
        }),
      });
      console.log("Session registrada en backend con access_token");
      statusBanner.innerText = "Avatar iniciado correctamente ✅";
    } else {
      statusBanner.innerText = "Error: no se pudo iniciar avatar ❌";
      console.warn("createStartAvatar no devolvió session_id.");
    }
  } catch (err) {
    statusBanner.innerText = "Error de conexión con backend ❌";
    console.error("Error iniciando avatar:", err);
  }
});

// === Consulta semántica con /api/query + hablar resultado ===
searchButton.addEventListener("click", async () => {
  const query = searchInput.value.trim();
  if (!query) {
    statusBanner.innerText = "Por favor escribe una consulta ⚠️";
    return;
  }

  statusBanner.innerText = "Esperando respuesta...";

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: currentMode, query: query })
    });
    const data = await res.json();

    searchResults.innerHTML = "";
    if (data.respuesta) {
      searchResults.innerHTML = `<p>${data.respuesta}</p>`;
      console.log("Respuesta del backend:", data.respuesta);
      statusBanner.innerText = "Respuesta recibida ✅";

      if (avatar && avatarReady) {
        await avatar.speak({
          text: data.respuesta,
          task_type: "REPEAT"
        });
        console.log("Texto enviado al avatar:", data.respuesta);
      } else {
        statusBanner.innerText = "Avatar aún no está listo ⚠️";
        console.warn("Avatar aún no está listo para hablar");
      }
    } else {
      statusBanner.innerText = "No se encontró respuesta ❌";
      searchResults.textContent = "No se encontraron resultados.";
    }
  } catch (err) {
    statusBanner.innerText = "Error en la consulta ❌";
    console.error("Error en búsqueda:", err);
    searchResults.textContent = "Error en la consulta.";
  }
});
