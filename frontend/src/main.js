import { Room, RoomEvent, createLocalAudioTrack } from "livekit-client";

// --- Métricas de performance ---
const marks = {};

function mark(label) {
  const t = performance.now();
  marks[label] = t;
}

function diff(start, end) {
  if (marks[start] && marks[end]) {
    const delta = marks[end] - marks[start];
    return delta;
  }
}

const videoElement = document.getElementById("avatarVideo");
const startButton = document.getElementById("startButton");
const avatarContainer = document.getElementById("avatarContainer");
const micSelect = document.getElementById("micSelect");
const transcriptDiv = document.getElementById("transcript"); // 👈 feedback en vivo

/** @type {import("livekit-client").Room | null} - Room cuando la sesión la inicia el backend (prestarted) */
let liveAvatarRoom = null;
/** Track del micrófono publicado en la sala; se mutea mientras el avatar habla para no interrumpir */
let publishedMicTrack = null;
/** Para logs USER_SPEECH_BEGIN / END / DURATION (eventos user.speak_started, user.speak_ended, user.transcription) */
let userSpeechStartTs = null;
let userSpeechEndTs = null;
/** Par start/end del turno actual; se fija en speak_ended para no mezclar con un speak_started posterior */
let pendingSpeechStartTs = null;
let pendingSpeechEndTs = null;
const LIVEKIT_AGENT_TOPIC = "agent-control";
const LIVEKIT_RESPONSE_TOPIC = "agent-response";
const HEYGEN_PARTICIPANT_ID = "heygen";
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
let lastFinalText = "";
let silenceTimer = null;
const SILENCE_COMMIT_MS = 900;
let sttEnabled = true;
let speechStartTs = null;
let lastDetectedText = "";
const USE_SDK_STT = false;
// Para QA: guardamos timestamps del último habla hasta enviar
let lastSpeechStartTs = null;
let lastSpeechEndTs = null;
let pendingQALog = null;

function resetSttState() {
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }
  lastFinalText = "";
}


function disableStt() {
  sttEnabled = false;
  resetSttState();
  try { browserRecognition?.abort(); } catch {}
  try { browserRecognition?.stop(); } catch {}
}

function enableStt() {
  sttEnabled = true;
  resetSttState();
  try { browserRecognition?.start(); } catch {}
}

function setListeningBackground() {
  document.body.classList.remove("speaking");
  document.body.classList.remove("hearing");
  document.body.classList.remove("listening");
  if (transcriptDiv) {
    transcriptDiv.innerHTML = "";
    transcriptDiv.style.display = "none";
  }
  console.log("Fondo: oyendo...");
}

function setUserSpeakingBackground() {
  document.body.classList.remove("speaking");
  document.body.classList.remove("hearing");
  document.body.classList.add("listening");
  console.log("Fondo: escuchando");
}

function setSpeakingBackground() {
  document.body.classList.add("speaking");
  document.body.classList.remove("hearing");
  document.body.classList.remove("listening");
  console.log("Fondo: avatar respondiendo");
}

function setHearingBackground() {
  if (document.body.classList.contains("speaking")) return;
  document.body.classList.add("hearing");
  console.log("Fondo: oyendo");
}

function clearHearingBackground() {
  document.body.classList.remove("hearing");
}

async function flushQALog(avatarStartTs) {
  if (!pendingQALog) return;
  const m = pendingQALog.metrics;
  if (avatarStartTs != null && m.speak_requested_ts != null) {
    m.avatar_start_ts = avatarStartTs;
    m.heygen_latency_ms = Math.round(avatarStartTs - m.speak_requested_ts);
  }
  try {
    await fetch("/api/qa/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: pendingQALog.query,
        response: pendingQALog.response,
        correction: null,
        metrics: m,
      }),
    });
  } catch (e) {
    console.warn("No se pudo guardar QA log:", e);
  }
  pendingQALog = null;
}


function handleBotResponse(userText, botText, qaContext) {
  const responseReceivedTs = performance.now();
  mark("response_received");
  console.log("AVATAR_RESPONDED:", botText);
  if (transcriptDiv) {
    transcriptDiv.innerHTML = `<div>Usuario: ${userText}</div>`;
    transcriptDiv.style.display = "block";
  }
  diff("audio_start", "response_received");
  pendingQALog = {
    query: userText,
    response: botText,
    metrics: {
      ...qaContext,
      response_received_ts: responseReceivedTs,
      llm_time_ms: qaContext?.llm_time_ms ?? null,
    },
  };
  if (botText) {
    handleAvatarSpeak(botText);
  } else {
    flushQALog(null);
  }
}

async function handleAvatarSpeak(text) {
  if (!avatarReady) {
    pendingSpeakQueue.push(text);
    console.warn("Avatar no listo aún, se encoló speak()");
    return;
  }
  const speakRequestedTs = performance.now();
  if (pendingQALog) pendingQALog.metrics.speak_requested_ts = speakRequestedTs;
  try {
    if (liveAvatarRoom && liveAvatarRoom.state === "connected") {
      const payload = { event_type: "avatar.speak_text", text };
      liveAvatarRoom.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify(payload)),
        { reliable: true, topic: LIVEKIT_AGENT_TOPIC }
      );
    }
  } catch (err) {
    console.error("Error invoking speak:", err);
    flushQALog(null);
  }
}

async function sendTranscriptViaHttp(text, speechMetrics = {}) {
  try {
    const t0 = performance.now();
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: currentMode || "Presentar",
        query: text,
        metrics: speechMetrics,
      }),
    });
    const t1 = performance.now();
    const data = await res.json();
    const llmTime = data?.llm_time_ms ?? Math.round(t1 - t0);
    console.log(`⏱️ tiempo chat gpt ${llmTime} ms`);
    const botText = data?.respuesta || data?.error || "";
    handleBotResponse(text, botText, {
      ...speechMetrics,
      llm_time_ms: data?.llm_time_ms ?? Math.round(t1 - t0),
    });
  } catch (e) {
    console.error("Error llamando /api/query:", e);
  }
}

/** Opción A: transcripción de Live Avatar (FULL mode) → ChatGPT → avatar.speak_text */
async function onLiveAvatarTranscription(userText) {
  try {
    const t0 = performance.now();
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: currentMode || "Presentar",
        query: userText,
        metrics: {},
      }),
    });
    const t1 = performance.now();
    const data = await res.json();
    const llmTime = data?.llm_time_ms ?? Math.round(t1 - t0);
    const botText = data?.respuesta || data?.error || "";
    console.log(`⏱️ [Live Avatar STT → ChatGPT] ${llmTime} ms`);
    handleBotResponse(userText, botText, { llm_time_ms: llmTime });
  } catch (e) {
    console.error("Error /api/query tras user.transcription:", e);
    flushQALog(null);
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

async function sendTranscript(text, speechMetrics = {}) {
  if (sendTranscriptViaWs(text)) return;
  if (ws) {
    console.warn("⚠️ WebSocket NO está OPEN, usando /api/query");
    console.warn("   Estado:", ws?.readyState);
    console.warn("   URL:", ws?.url);
    console.warn("   bufferedAmount:", ws?.bufferedAmount);
  } else {
    console.log("ℹ️ WS desactivado, usando /api/query");
  }
  await sendTranscriptViaHttp(text, speechMetrics);
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
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const hint = json.hint ? "\n\n" + json.hint : "";
      const details = json.details;
      const detailsStr = typeof details === "string" ? details : (details?.message || details?.error || resp.statusText || "Error desconocido");
      throw new Error(detailsStr + hint);
    }
    const { avatar_id, voice_id } = json;
    console.log("Session start data:", json);

    globalVoiceId = voice_id;
    globalAvatarId = avatar_id;

    if (!json.prestarted || !json.livekit_url || !json.livekit_client_token) {
      alert("El backend no devolvió sesión Live Avatar (livekit_url / livekit_client_token).");
      return;
    }

    // --- Live Avatar (prestarted): backend ya llamó start; conectamos con Room a LiveKit ---
    liveAvatarRoom = new Room();
    const mediaStream = new MediaStream();

    liveAvatarRoom.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
      if (participant.identity !== HEYGEN_PARTICIPANT_ID) return;
      if (track.kind === "video" || track.kind === "audio") {
        mediaStream.addTrack(track.mediaStreamTrack);
        const hasVideo = mediaStream.getVideoTracks().length > 0;
        const hasAudio = mediaStream.getAudioTracks().length > 0;
        if (hasVideo && hasAudio && videoElement) {
          videoElement.srcObject = mediaStream;
          videoElement.volume = 1.0;
          videoElement.muted = false;
          videoElement.onloadedmetadata = () => videoElement.play().catch(console.error);
          avatarReady = true;
          if (pendingSpeakQueue.length > 0) {
            const queue = pendingSpeakQueue;
            pendingSpeakQueue = [];
            queue.reduce((p, t) => p.then(() => handleAvatarSpeak(t)), Promise.resolve());
          }
          console.log("LiveAvatar prestarted SESSION_STREAM_READY");
        }
      }
    });

    liveAvatarRoom.on(RoomEvent.DataReceived, (msg, _p, _r, topic) => {
      if (topic !== LIVEKIT_RESPONSE_TOPIC) return;
      try {
        const ev = JSON.parse(new TextDecoder().decode(msg));
        if (ev.event_type === "avatar.speak_started") {
          const avatarStartTs = performance.now();
          flushQALog(avatarStartTs);
          setSpeakingBackground();
          isSpeaking = true;
          disableStt();
        } else if (ev.event_type === "avatar.speak_ended") {
          isSpeaking = false;
          enableStt();
          setListeningBackground();
          if (publishedMicTrack) publishedMicTrack.unmute();
        } else if (ev.event_type === "user.speak_started") {
          userSpeechStartTs = performance.now();
          console.log("USER_SPEAK_BEGIN", Math.round(performance.now()));
          setUserSpeakingBackground();
        } else if (ev.event_type === "user.speak_ended") {
          userSpeechEndTs = performance.now();
          pendingSpeechStartTs = userSpeechStartTs;
          pendingSpeechEndTs = userSpeechEndTs;
        } else if (ev.event_type === "user.transcription") {
          const text = (ev.text || "").trim();
          const now = performance.now();
          const durationMs = userSpeechStartTs != null ? Math.max(0, Math.round(now - userSpeechStartTs)) : 0;
          console.log("USER_SPEAK_ENDED", Math.round(now), ", DURATION", durationMs, "ms, TRANSCRIPTION", text);
          setListeningBackground();
          // Opción A: STT de Live Avatar → interrumpir su LLM → ChatGPT → avatar.speak_text
          if (!text || text.length < 2) return;
          if (publishedMicTrack) publishedMicTrack.mute();
          // Cancelar respuesta automática del LLM de Live Avatar
          try {
            liveAvatarRoom.localParticipant.publishData(
              new TextEncoder().encode(JSON.stringify({ event_type: "avatar.interrupt" })),
              { reliable: true, topic: LIVEKIT_AGENT_TOPIC }
            );
          } catch (e) {
            console.warn("avatar.interrupt error:", e);
          }
          // Llamar a nuestro LLM (ChatGPT) y luego hacer hablar al avatar
          onLiveAvatarTranscription(text);
        }
      } catch (_) {}
    });

    await liveAvatarRoom.connect(json.livekit_url, json.livekit_client_token);

    // Opción A: publicar micrófono para que Live Avatar haga STT (FULL mode) y emitir user.transcription
    const audioTrack = await createLocalAudioTrack({
      deviceId: micSelect?.value ? { exact: micSelect.value } : undefined,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: false,
    });
    await liveAvatarRoom.localParticipant.publishTrack(audioTrack, { name: "microphone" });
    publishedMicTrack = audioTrack;
    micSelect.disabled = true;
    setListeningBackground();
    console.log("🎤 Micrófono publicado en la sala; Live Avatar STT activo (user.transcription → ChatGPT → avatar.speak_text)");
  } catch (err) {
    console.error("Error iniciando avatar:", err);
    const msg = (err.message || String(err)).slice(0, 300);
    alert("Error iniciando avatar: " + (msg.length >= 300 ? msg + "…" : msg));
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
  recognition.lang = "es-AR";
  recognition.continuous = true;  // Escucha continua
  recognition.interimResults = true;  // Parciales para feedback inmediato
  recognition.maxAlternatives = 1;

  let isProcessing = false;

  recognition.onstart = () => {
    console.log("🟢 SpeechRecognition iniciado (escuchando...)");
    setListeningBackground();
  };

  recognition.onspeechstart = () => {
    setHearingBackground();
    speechStartTs = performance.now();
    console.log(`SPEECH INIT ${Math.round(speechStartTs)}ms`);
  };

  recognition.onspeechend = () => {
    clearHearingBackground();
    const endTs = performance.now();
    console.log(`SPEECH END ${Math.round(endTs)}ms`);
    if (speechStartTs != null) {
      lastSpeechStartTs = speechStartTs;
      lastSpeechEndTs = endTs;
      console.log(`SPEECH DURATION ${Math.round(endTs - speechStartTs)}ms`);
      if (lastDetectedText) {
        console.log(`SPEECH DETECTED ${lastDetectedText}`);
      }
    }
    speechStartTs = null;
  };

  const normalizeTranscript = (text) => {
    let t = (text || "").trim();
    if (!t) return "";
    // Quitar fillers comunes
    t = t.replace(/\b(eh|emm|mmm|este|a ver)\b/gi, "").replace(/\s{2,}/g, " ").trim();
    // Capitalizar inicio
    t = t.charAt(0).toUpperCase() + t.slice(1);
    return t;
  };

  const scheduleFinalCommit = () => {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    silenceTimer = setTimeout(async () => {
      const finalText = normalizeTranscript(lastFinalText);
      if (!finalText) return;
      lastFinalText = "";
      mark("audio_start");
      mark("audio_stop");
      const speechMetrics = {
        speech_start_ts: lastSpeechStartTs,
        speech_end_ts: lastSpeechEndTs,
        speech_duration_ms: lastSpeechStartTs != null && lastSpeechEndTs != null
          ? Math.round(lastSpeechEndTs - lastSpeechStartTs) : null,
      };
      console.log("🎙️ Detectado (final):", finalText);
      console.log("📤 Enviando transcripción al backend...");
      await sendTranscript(finalText, speechMetrics);
      lastSpeechStartTs = null;
      lastSpeechEndTs = null;
      silenceTimer = null;
    }, SILENCE_COMMIT_MS);
  };

  recognition.onresult = async (event) => {
    if (!sttEnabled || isSpeaking) return;
    let interimText = "";
    let finalText = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const res = event.results[i];
      const text = res[0]?.transcript || "";
      if (res.isFinal) {
        finalText += text;
      } else {
        interimText += text;
      }
    }

    const interim = interimText.trim();
    const final = finalText.trim();

    if (interim) {
      lastDetectedText = interim;
      if (transcriptDiv) {
        transcriptDiv.innerHTML = `<div>Usuario: ${interim}</div>`;
        transcriptDiv.style.display = "block";
      }
    }

    if (final) {
      lastDetectedText = final;
      lastFinalText = `${lastFinalText} ${final}`.trim();
      scheduleFinalCommit();
    }

    if (isProcessing) return;
    isProcessing = true;
    setTimeout(() => { isProcessing = false; }, 600);
  };

  recognition.onerror = (event) => {
    console.warn("⚠️ SpeechRecognition error:", event.error);
    if (event.error === "no-speech") {
      console.log("Sin speech detectado, continuando...");
    }
    resetSttState();
    isProcessing = false;
  };

  recognition.onend = () => {
    if (isSpeaking) {
      return;
    }
    resetSttState();
    if (!sttEnabled) {
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

      // 👉 Disparar la voz (LiveAvatar o HeyGen)
      try {
        await handleAvatarSpeak(respuestaTexto);
      } catch (err) {
        console.error("Error invoking speak:", err);
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

      // 👉 Disparar la voz (LiveAvatar o HeyGen)
      await handleAvatarSpeak(texto);
    }
    while (transcriptDiv.childNodes.length > 50) {
      transcriptDiv.removeChild(transcriptDiv.firstChild);
    }

  } catch (err) {
    console.error("Error en la consulta: ", err);
  }
}
