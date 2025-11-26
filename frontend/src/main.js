import StreamingAvatar, { StreamingEvents } from "@heygen/streaming-avatar";

// Elementos del DOM
const videoElement = document.getElementById("avatarVideo");
const startButton = document.getElementById("startButton");
const speakButton = document.getElementById("speakButton");

// Variables globales
let avatar = null;

// 1) Iniciar avatar al hacer click en "Start"
startButton.addEventListener("click", async () => {
  console.log("=== Iniciando avatar ===");

  // Llamar al backend para obtener token y parámetros
  const resp = await fetch("/api/session/start", { method: "POST" });
  const json = await resp.json();

  const token = json.data?.token;
  const avatar_id = json.avatar_id;
  const voice_id = json.voice_id;
  const language = json.language;

  console.log("=== Datos recibidos del backend ===");
  console.log("Token:", token);
  console.log("Avatar ID:", avatar_id);
  console.log("Voice ID:", voice_id);
  console.log("Language:", language);

  // Crear instancia de avatar
  avatar = new StreamingAvatar({ token });
  console.log("Instancia de avatar creada");

  // 2) Escuchar evento STREAM_READY (video + audio)
avatar.on(StreamingEvents.STREAM_READY, (event) => {
  console.log("=== STREAM_READY ===");
  if (event.detail && videoElement) {
    // Conectar el stream completo (video + audio)
    videoElement.srcObject = event.detail;

    // 👉 Asegurar volumen
    videoElement.volume = 1.0; // aquí va la línea que mencionábamos

    videoElement.onloadedmetadata = () => {
      videoElement.play().catch(console.error);
    };
    console.log("Video + audio conectados al avatar");
  }
});

  // 3) Escuchar otros eventos útiles
  avatar.on(StreamingEvents.AVATAR_STARTED, () => {
    console.log("Avatar inicializado");
  });

  avatar.on(StreamingEvents.TRANSCRIPTION, (event) => {
    console.log("Transcripción final:", event.detail);
  });

  // 4) Iniciar avatar con parámetros
  await avatar.createStartAvatar({
    avatarName: avatar_id,
    voiceId: voice_id,
    language: language,
    quality: "high",
    video: true,
  });

  console.log("Avatar iniciado con createStartAvatar");
});

// 5) Botón para enviar texto al avatar
speakButton.addEventListener("click", async () => {
  if (!avatar) return;
  console.log("Texto enviado con speak()");
  await avatar.speak({ text: "Hello Rodrigo, how are you today?" });
});
