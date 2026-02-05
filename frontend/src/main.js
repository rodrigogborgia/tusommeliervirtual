import StreamingAvatar, { StreamingEvents, TaskMode, TaskType } from "@heygen/streaming-avatar";

// --- Métricas de performance ---
const marks = {};

function mark(label) {
  const t = performance.now();
  marks[label] = t;
  console.log(`MARK: ${label}`, Math.round(t));
}

function diff(start, end) {
  if (marks[start] && marks[end]) {
    const delta = marks[end] - marks[start];
    console.log(`DIFF ${start} -> ${end}: ${Math.round(delta)} ms`);
    return delta;
  }
}

const videoElement = document.getElementById("avatarVideo");
const startButton = document.getElementById("startButton");
const avatarContainer = document.getElementById("avatarContainer");
const micSelect = document.getElementById("micSelect");
const transcriptDiv = document.getElementById("transcript"); // 👈 feedback en vivo

let avatar = null;
let sessionId = null;
let accessToken = null;
let avatarReady = false;
let currentMode = "Presentar";
let audioCtx, sourceNode, processorNode, ws;

// 👉 variables globales para voz y avatar
let globalVoiceId = null;
let globalAvatarId = null;

// Para no spamear MARK: audio_start por cada chunk
let audioInUtterance = false;
let pendingSpeakQueue = [];
let browserRecognition = null;
let isSpeaking = false;

function setListeningBackground() {
  document.body.classList.remove("speaking");
  document.body.classList.remove("hearing");
  if (transcriptDiv) {
    transcriptDiv.innerHTML = "";
    transcriptDiv.style.display = "none";
  }
  console.log("🎨 Fondo: escuchando");
}

function setSpeakingBackground() {
  document.body.classList.add("speaking");
  document.body.classList.remove("hearing");
  console.log("🎨 Fondo: hablando");
}

function setHearingBackground() {
  if (document.body.classList.contains("speaking")) return;
  document.body.classList.add("hearing");
  console.log("🎨 Fondo: oyendo");
}

function clearHearingBackground() {
  document.body.classList.remove("hearing");
}


function handleBotResponse(userText, botText) {
  mark("response_received");
  console.log("USER_SAID:", userText);
  console.log("AVATAR_RESPONDED:", botText);
  if (transcriptDiv) {
    transcriptDiv.innerHTML = `<div>Usuario: ${userText}</div><div>Sommelier: ${botText}</div>`;
    transcriptDiv.style.display = "block";
  }
  diff("audio_start", "response_received");
  if (botText) {
    handleAvatarSpeak(botText);
  }
}

async function handleAvatarSpeak(text) {
  if (!avatar || !avatarReady) {
    // Guardar para reproducir cuando el avatar esté listo
    pendingSpeakQueue.push(text);
    console.warn("Avatar no listo aún, se encoló speak()");
    return;
  }
  try {
    await avatar.speak({
      text,
      task_type: TaskType.REPEAT,
      taskMode: TaskMode.SYNC,
    });
  } catch (err) {
    console.error("Error invoking speak:", err);
  }
}

async function sendTranscriptViaHttp(text) {
  try {
    const t0 = performance.now();
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: currentMode || "Presentar", query: text }),
    });
    const t1 = performance.now();
    const data = await res.json();
    console.log(`⏱️ tiempo chat gpt ${Math.round(t1 - t0)} ms`);
    const botText = data?.respuesta || data?.error || "";
    handleBotResponse(text, botText);
  } catch (e) {
    console.error("Error llamando /api/query:", e);
  }
}

function sendTranscriptViaWs(text) {
  if (ws?.readyState !== WebSocket.OPEN) return false;
  const payload = {
    type: "transcript",
    text,
    timestamp: performance.now(),
  };
  console.log("📤 Payload:", payload);
  ws.send(JSON.stringify(payload));
  console.log("✅ Transcripción enviada al WebSocket");
  return true;
}

async function sendTranscript(text) {
  if (sendTranscriptViaWs(text)) return;
  if (ws) {
    console.warn("⚠️ WebSocket NO está OPEN, usando /api/query");
    console.warn("   Estado:", ws?.readyState);
    console.warn("   URL:", ws?.url);
    console.warn("   bufferedAmount:", ws?.bufferedAmount);
  } else {
    console.log("ℹ️ WS desactivado, usando /api/query");
  }
  await sendTranscriptViaHttp(text);
}

async function ensureMicPermission() {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
    return true;
  } catch (e) {
    console.warn("Permiso de micrófono rechazado o no disponible:", e);
    return false;
  }
}

function cleanupAudio() {
  try { processorNode?.disconnect(); } catch {}
  try { sourceNode?.disconnect(); } catch {}
  try { if (processorNode?.port) processorNode.port.onmessage = null; } catch {}
  try { if (audioCtx && audioCtx.state !== "closed") audioCtx.close(); } catch {}
  audioCtx = null;
  sourceNode = null;
  processorNode = null;
}

// === Poblar selector de micrófono ===
async function populateMicSelect() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  micSelect.innerHTML = "";
  devices.filter(d => d.kind === "audioinput").forEach((d, idx) => {
    const option = document.createElement("option");
    option.value = d.deviceId;
    option.text = d.label || `Micrófono ${idx + 1}`;
    micSelect.appendChild(option);
  });
}
populateMicSelect();

micSelect.addEventListener("change", () => {
  console.log("Micrófono seleccionado:", micSelect.value);
});


// === Iniciar avatar ===
startButton.addEventListener("click", async () => {
  startButton.style.display = "none";
  avatarContainer.style.display = "block";
  if (micSelect) micSelect.style.display = "none";

  try {
    // Si no pedimos permiso antes, Chrome no muestra labels reales y queda "Micrófono 1"
    await ensureMicPermission();
    await populateMicSelect();

    const resp = await fetch("/api/session/start", { method: "POST" });
    if (!resp.ok) throw new Error(`Error iniciando avatar: ${resp.status} ${resp.statusText}`);

    const json = await resp.json();
    const { token, avatar_id, voice_id, language } = json;
    console.log("Session start data:", json);

    // 👉 guardar en variables globales
    globalVoiceId = voice_id;
    globalAvatarId = avatar_id;

    if (!token) {
      alert("No se recibió token desde el backend.");
      return;
    }

    // 👉 Crear instancia del avatar con el token
    avatar = new StreamingAvatar({ token });

    // 👉 Eventos de habla para manejar fondo y pausa de escucha
    avatar.on(StreamingEvents.AVATAR_START_TALKING, () => {
      setSpeakingBackground();
      isSpeaking = true;
      try { browserRecognition?.stop(); } catch {}
    });
    avatar.on(StreamingEvents.AVATAR_STOP_TALKING, () => {
      isSpeaking = false;
      try { browserRecognition?.start(); } catch {}
      setListeningBackground();
    });

    // 👉 Enganchar STREAM_READY: entrega video + audio
    avatar.on(StreamingEvents.STREAM_READY, (event) => {
      if (event.detail && videoElement) {
        videoElement.srcObject = event.detail;
        videoElement.volume = 1.0;
        videoElement.muted = false;
        videoElement.onloadedmetadata = () => {
          videoElement.play().catch(console.error);
        };
        // 👉 Métricas de reproducción
        videoElement.onplay = () => {
          mark("avatar_start");
          ws?.send(JSON.stringify({ type: "mark", label: "avatar_start", ts: performance.now() }));
        };
        videoElement.onended = () => {
          mark("avatar_done");
          ws?.send(JSON.stringify({ type: "mark", label: "avatar_done", ts: performance.now() }));
          mark("interaction_end");
          ws?.send(JSON.stringify({ type: "mark", label: "interaction_end", ts: performance.now() }));
          diff("audio_start", "avatar_done");
          diff("interaction_start", "interaction_end");
        };
      }
      avatarReady = true;
      if (pendingSpeakQueue.length > 0) {
        const queue = pendingSpeakQueue;
        pendingSpeakQueue = [];
        // Reproducir en orden las respuestas pendientes
        queue.reduce(
          (p, t) => p.then(() => handleAvatarSpeak(t)),
          Promise.resolve()
        );
      }
      console.log("STREAM_READY recibido, avatar conectado con audio+video");
      console.log("SDK session_id activo:", avatar.sessionId);
    });

    // 👉 Crear sesión en HeyGen
    const sessionInfo = await avatar.createStartAvatar({
      avatarName: avatar_id,
      voiceId: voice_id,
      language,
      quality: "high",
      video: true
    });

    if (sessionInfo?.session_id && sessionInfo?.access_token) {
      sessionId = sessionInfo.session_id;
      accessToken = sessionInfo.access_token;
      console.log("createStartAvatar devolvió:", sessionId, accessToken);

      await fetch("/api/session/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, access_token: accessToken }),
      });

      // 👉 preparar audio del micrófono
      const constraints = {
        audio: {
          deviceId: micSelect.value ? { exact: micSelect.value } : undefined,
          echoCancellation: true,
          noiseSuppression: true,
          // En muchos mics USB el AGC amplifica el hiss/ruido y provoca "alucinaciones" en STT.
          autoGainControl: false,
          channelCount: 1,
        }
      };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      console.log("Micrófono en uso:", micSelect.value);
      micSelect.disabled = true;
      try { stream.getTracks().forEach((t) => t.stop()); } catch {}

      // 👉 Usar STT nativo del navegador
      await startListeningBrowserSTT(stream);
    } else {
      console.error("Respuesta inesperada de createStartAvatar:", sessionInfo);
      alert("No se pudo iniciar la sesión del avatar (faltan credenciales).");
    }

  } catch (err) {
    console.error("Error iniciando avatar:", err);
    alert("Error iniciando avatar. Revisá la consola.");
  }
});

// === STT nativo del navegador (Web Speech API) ===
async function startListeningBrowserSTT(stream) {
  console.log("🎤 Usando STT nativo del navegador (SpeechRecognition)");
  setListeningBackground();
  
  // Verificar compatibilidad
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Tu navegador no soporta Web Speech API. Usá Chrome/Edge.");
    return;
  }

  // WS desactivado; usamos /api/query
  ws = null;

  const recognition = new SpeechRecognition();
  browserRecognition = recognition;
  recognition.lang = "es-ES";
  recognition.continuous = true;  // Escucha continua
  recognition.interimResults = false;  // Solo resultados finales (más confiables)
  recognition.maxAlternatives = 1;

  let isProcessing = false;

  recognition.onstart = () => {
    console.log("🟢 SpeechRecognition iniciado (escuchando...)");
    setListeningBackground();
  };

  recognition.onspeechstart = () => {
    setHearingBackground();
  };

  recognition.onspeechend = () => {
    clearHearingBackground();
  };

  recognition.onresult = async (event) => {
    const last = event.results.length - 1;
    const transcript = event.results[last][0].transcript.trim();
    
    if (!transcript || isProcessing) return;

    isProcessing = true;
    mark("audio_start");
    console.log("🎙️ Detectado:", transcript);
    mark("audio_stop");
    console.log("📤 Enviando transcripción al backend...");
    await sendTranscript(transcript);

    // Reset flag después de un delay para permitir nuevas frases
    setTimeout(() => { isProcessing = false; }, 2000);
  };

  recognition.onerror = (event) => {
    console.warn("⚠️ SpeechRecognition error:", event.error);
    if (event.error === "no-speech") {
      console.log("Sin speech detectado, continuando...");
    }
    isProcessing = false;
  };

  recognition.onend = () => {
    if (isSpeaking) {
      return;
    }
    console.log("🔄 SpeechRecognition terminó, reiniciando...");
    try {
      recognition.start();
    } catch (e) {
      console.warn("No se pudo reiniciar recognition:", e);
    }
  };

  try {
    recognition.start();
    console.log("✅ STT del navegador activado");
  } catch (e) {
    console.error("Error iniciando SpeechRecognition:", e);
  }
}

// === WebSocket de audio (LEGACY - ahora se usa browser STT) ===
async function startListeningWebSocket(stream) {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/audio`);

  ws.onopen = async () => {
    mark("interaction_start");
    console.log("Registrando WS con:", sessionId, accessToken);
    ws.send(JSON.stringify({ type: "mark", label: "interaction_start", ts: performance.now() }));

    // 👇 ahora enviamos también el access_token
    ws.send(JSON.stringify({
      type: "register",
      session_id: sessionId,
      access_token: accessToken
    }));

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    await audioCtx.audioWorklet.addModule("processor.js");

    sourceNode = audioCtx.createMediaStreamSource(stream);
    processorNode = new AudioWorkletNode(audioCtx, "pcm-processor");

    processorNode.port.onmessage = (event) => {
      if (event.data.type === "audio") {
        const pcm16 = floatTo16BitPCM(event.data.data);
        if (ws?.readyState === WebSocket.OPEN) {
          // Marcar audio_start solo una vez por frase
          if (!audioInUtterance) {
            audioInUtterance = true;
            mark("audio_start");
            ws.send(JSON.stringify({ type: "mark", label: "audio_start", ts: performance.now() }));
          }
          ws.send(pcm16);
        }
      } else if (event.data.type === "end_of_utterance") {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(new Uint8Array(0));
          // Coherencia de métricas: marcar fin de frase
          mark("audio_stop");
          ws.send(JSON.stringify({ type: "mark", label: "audio_stop", ts: performance.now() }));
          mark("waiting_response");
          ws.send(JSON.stringify({ type: "mark", label: "waiting_response", ts: performance.now() }));
          audioInUtterance = false;
        }
      }
    };

    sourceNode.connect(processorNode);
  };

  ws.onmessage = async (evt) => {
  try {
    const msg = JSON.parse(evt.data);

    // 👉 marcar recepción de respuesta
    mark("response_received");
    ws.send(JSON.stringify({ 
      type: "mark", 
      label: "response_received", 
      ts: performance.now() 
    }));

    // 👉 mostrar transcripción del usuario
    if (msg.text) {
      console.log("USER_SAID:", msg.text);
      transcriptDiv.innerHTML += `<p><b>Usuario:</b> ${msg.text}</p>`;
      ws.send(JSON.stringify({ 
        type: "mark", 
        label: `USER_SAID: ${msg.text}`, 
        ts: performance.now() 
      }));
    }

    // 👉 mostrar respuesta del avatar
    if (msg.respuesta) {
      const respuestaTexto = msg.respuesta?.respuesta || msg.respuesta;
      console.log("AVATAR_RESPONDED:", respuestaTexto);
      transcriptDiv.innerHTML += `<p><b>Avatar:</b> ${respuestaTexto}</p>`;
      ws.send(JSON.stringify({ 
        type: "mark", 
        label: `AVATAR_RESPONDED: ${respuestaTexto}`, 
        ts: performance.now() 
      }));

      // 👉 Disparar la voz directamente desde el SDK
      if (avatar) {
        try {
          await avatar.speak({
            text: respuestaTexto,
            // SpeakRequest (SDK): { text, task_type/taskType, taskMode }
            task_type: TaskType.REPEAT, // porque tu LLM ya arma el texto
            taskMode: TaskMode.ASYNC,
          });
        } catch (err) {
          console.error("Error invoking speak:", err);
        }
      } else {
        console.warn("Avatar no inicializado aún, se omitió speak()");
      }
    }

    // 👉 limpiar transcripciones si se acumulan demasiadas
    if (transcriptDiv.childNodes.length > 50) {
      transcriptDiv.innerHTML = "<p><i>Historial limpiado para mantener rendimiento</i></p>";
    }

  } catch (err) {
    console.error("Error procesando mensaje WS:", err);
  }
};

// 👉 manejo de errores y cierre de WS
ws.onerror = (err) => {
  console.error("Error en WS audio:", err);
  cleanupAudio();
};

ws.onclose = () => {
  console.log("WS cerrado, audio liberado");
  cleanupAudio();
  setTimeout(() => startListeningWebSocket(stream), 2000);
};
}

function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0, offset = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

// === Consulta semántica ===
async function enviarConsulta(query) {
  if (!query) return;

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: currentMode, query })
    });
    const data = await res.json();

    if (data.respuesta) {
      const texto = data.respuesta?.respuesta || data.respuesta;

      transcriptDiv.innerHTML += `<p><b>Avatar:</b> ${texto}</p>`;
      ws?.send(JSON.stringify({ type: "mark", label: `AVATAR_RESPONDED: ${texto}`, ts: performance.now() }));

      console.log("AVATAR_RESPONDED (consulta):", texto);

      // 👉 Disparar la voz desde el SDK solo si el avatar está listo
      if (avatar && avatarReady) {
        await avatar.speak({
          text: texto,
          task_type: TaskType.REPEAT,
          taskMode: TaskMode.ASYNC,
        });
      } else {
        console.warn("Avatar no listo aún, se omitió addTask");
      }
    }
    while (transcriptDiv.childNodes.length > 50) {
      transcriptDiv.removeChild(transcriptDiv.firstChild);
    }

  } catch (err) {
    console.error("Error en la consulta: ", err);
  }
}
