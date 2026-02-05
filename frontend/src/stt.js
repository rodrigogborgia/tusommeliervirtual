const micSelect = document.getElementById("micSelect");
const btnStart = document.getElementById("btnStart");
const btnStop = document.getElementById("btnStop");
const transcriptDiv = document.getElementById("transcript");
const backendStatus = document.getElementById("backendStatus");
const wsStatus = document.getElementById("wsStatus");
const listenStatus = document.getElementById("listenStatus");
const lastAudioEl = document.getElementById("lastAudio");
const downloadWavEl = document.getElementById("downloadWav");

// Flags por URL para debug
const urlParams = new URLSearchParams(location.search);
// Modo mínimo: solo loguear eventos del STT del navegador (sin WS / sin audio / sin worklet)
// Uso: /stt.html?debug=browser_events
const debugBrowserEventsOnly = (urlParams.get("debug") || "").toLowerCase() === "browser_events";

let audioCtx = null;
let sourceNode = null;
let processorNode = null;
let ws = null;
let stream = null;
let audioInUtterance = false;
let utteranceChunks = [];
let utteranceBytes = 0;
let lastObjectUrl = null;

// --- Modo opcional: sincronizar inicio/fin de frase usando SpeechRecognition del navegador ---
// Activación por URL: /stt.html?sync=browserstt
const browserSyncEnabled = (urlParams.get("sync") || "").toLowerCase() === "browserstt";
let browserSpeechActive = false;
let pendingSyncFinalizeTimer = null;

// Pre-roll: para no perder el inicio si el evento onspeechstart llega tarde
const PRE_ROLL_MAX_MS = 250;
const PRE_ROLL_MAX_BYTES = Math.floor(16000 * 2 * (PRE_ROLL_MAX_MS / 1000)); // 16kHz * 16-bit * segundos
let preRollChunks = [];
let preRollBytes = 0;

// --- Browser STT (solo debug) ---
const BrowserSpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let browserRec = null;
let browserSttEnabled = false;
let browserSttStopping = false;
let lastBrowserInterim = "";
let lastBrowserFinal = "";
let lastBrowserInterimAt = 0;

const marks = {};
function mark(label) {
  const t = Math.round(performance.now());
  marks[label] = t;
  console.log(`MARK: ${label}`, t);
}

// --- Debug "solo eventos": output ultra simple para consola ---
let dbgUtteranceActive = false;
let dbgStartTs = 0;
let dbgEndPendingTs = 0;
let dbgFinalText = "";
let dbgInterimText = "";
let dbgEndTimer = null;
let dbgInactivityTimer = null;
let dbgLastResultTs = 0;

function dbgResetUtterance() {
  dbgUtteranceActive = false;
  dbgStartTs = 0;
  dbgEndPendingTs = 0;
  dbgFinalText = "";
  dbgInterimText = "";
  dbgLastResultTs = 0;
  if (dbgEndTimer) {
    clearTimeout(dbgEndTimer);
    dbgEndTimer = null;
  }
  if (dbgInactivityTimer) {
    clearTimeout(dbgInactivityTimer);
    dbgInactivityTimer = null;
  }
}

function dbgEmitStart(ts) {
  if (dbgUtteranceActive) return;
  dbgUtteranceActive = true;
  dbgStartTs = ts;
  dbgFinalText = "";
  dbgInterimText = "";
  dbgEndPendingTs = 0;
  console.log(`STT_START: ${ts}`);
}

function dbgEmitEnd(ts, text) {
  if (!dbgUtteranceActive) return;
  const safe = (text || "").replaceAll('"', '\\"');
  console.log(`STT_END: ${ts}, "${safe}"`);
  dbgResetUtterance();
}

function dbgScheduleEnd(ts) {
  if (!dbgUtteranceActive) return;
  dbgEndPendingTs = ts;
  // Muchas veces el FINAL llega después del "speechend"; esperamos un poco,
  // pero si no llega, usamos el mejor texto disponible (final o interim).
  if (dbgEndTimer) clearTimeout(dbgEndTimer);
  dbgEndTimer = setTimeout(() => {
    dbgEndTimer = null;
    const outText = dbgFinalText || dbgInterimText || "";
    dbgEmitEnd(dbgEndPendingTs, outText);
  }, 450);

  // Si ya tenemos final, emitimos de inmediato
  if (dbgFinalText) {
    dbgEmitEnd(dbgEndPendingTs, dbgFinalText);
  }
}

function dbgKickInactivityTimer() {
  if (!dbgUtteranceActive) return;
  if (dbgInactivityTimer) clearTimeout(dbgInactivityTimer);
  dbgInactivityTimer = setTimeout(() => {
    dbgInactivityTimer = null;
    // Si pasan ~700ms sin nuevos resultados, asumimos fin de frase.
    const now = Math.round(performance.now());
    const text = dbgFinalText || dbgInterimText || "";
    dbgEmitEnd(now, text);
  }, 700);
}

function buildWavDebugFromPcm(pcmAll) {
  // Construir WAV de la frase para escuchar exactamente lo enviado a STT
  try {
    const wav = pcm16ToWavBlob(pcmAll, 16000);
    if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl);
    lastObjectUrl = URL.createObjectURL(wav);

    // UI + download
    if (lastAudioEl) lastAudioEl.src = lastObjectUrl;
    if (downloadWavEl) downloadWavEl.href = lastObjectUrl;

    // Console preview (no spamear todo el vector)
    const i16 = new Int16Array(pcmAll.buffer, pcmAll.byteOffset, Math.floor(pcmAll.byteLength / 2));
    const preview = Array.from(i16.slice(0, 64));
    const dur = (pcmAll.byteLength / (16000 * 2)).toFixed(2);
    console.log("UTTERANCE_WAV_URL:", lastObjectUrl);
    console.log("UTTERANCE_META:", { bytes: pcmAll.byteLength, seconds: Number(dur) });
    console.log("UTTERANCE_PCM16_PREVIEW(first64):", preview);
  } catch (e) {
    console.warn("No se pudo construir WAV de debug:", e);
  }
}

function resetUtteranceBuffers() {
  utteranceChunks = [];
  utteranceBytes = 0;
}

function resetPreRoll() {
  preRollChunks = [];
  preRollBytes = 0;
}

function pushPreRoll(pcm16u8) {
  preRollChunks.push(pcm16u8);
  preRollBytes += pcm16u8.byteLength;
  while (preRollBytes > PRE_ROLL_MAX_BYTES && preRollChunks.length > 1) {
    const rm = preRollChunks.shift();
    preRollBytes -= rm.byteLength;
  }
}

function beginUtteranceIfNeeded() {
  if (audioInUtterance) return;
  audioInUtterance = true;
  mark("audio_start");
  try {
    ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "mark", label: "audio_start", ts: performance.now() }));
  } catch {}

  // Precargar con pre-roll (si existe)
  utteranceChunks = preRollChunks.slice();
  utteranceBytes = preRollBytes;
}

function finalizeUtteranceAndSend(reason = "browser_speech_end") {
  if (!audioInUtterance) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    audioInUtterance = false;
    resetUtteranceBuffers();
    return;
  }

  // evitar dobles flush por eventos duplicados
  if (pendingSyncFinalizeTimer) {
    clearTimeout(pendingSyncFinalizeTimer);
    pendingSyncFinalizeTimer = null;
  }

  const pcmAll = concatChunks(utteranceChunks, utteranceBytes);
  ws.send(pcmAll);
  ws.send(new Uint8Array(0));

  mark("audio_stop");
  ws.send(JSON.stringify({ type: "mark", label: "audio_stop", ts: performance.now() }));
  mark("waiting_response");
  ws.send(JSON.stringify({ type: "mark", label: "waiting_response", ts: performance.now() }));
  audioInUtterance = false;

  // Debug local de WAV
  buildWavDebugFromPcm(pcmAll);
  resetUtteranceBuffers();
  resetPreRoll();
  console.log("BROWSER_STT_SYNC_FLUSH reason:", reason);
}

function scheduleSyncFinalize(reason, delayMs = 200) {
  if (!browserSyncEnabled) return;
  if (!audioInUtterance) return;
  if (pendingSyncFinalizeTimer) clearTimeout(pendingSyncFinalizeTimer);
  pendingSyncFinalizeTimer = setTimeout(() => {
    pendingSyncFinalizeTimer = null;
    finalizeUtteranceAndSend(reason);
  }, delayMs);
}

function startBrowserSttDebug() {
  if (!BrowserSpeechRecognition) {
    console.log("BROWSER_STT: no disponible en este navegador (SpeechRecognition no existe).");
    if (browserSyncEnabled) {
      console.warn("BROWSER_STT_SYNC: no disponible (sin SpeechRecognition). Usando VAD del worklet.");
    }
    return;
  }
  if (browserRec) return;

  try {
    browserRec = new BrowserSpeechRecognition();
    browserRec.lang = "es-ES";
    // En modo eventos, necesitamos onresult para capturar el FINAL (aunque ignoremos interim).
    browserRec.interimResults = true;
    browserRec.continuous = true;

    browserRec.onstart = () => {
      browserSttEnabled = true;
      browserSttStopping = false;
      if (!debugBrowserEventsOnly) {
        mark("browser_stt_start");
        console.log("BROWSER_STT: started");
      }
    };

    // Eventos de habla (usables como "sincronizador" de frase).
    browserRec.onspeechstart = () => {
      const ts = Math.round(performance.now());
      if (debugBrowserEventsOnly) dbgEmitStart(ts);
      else {
        mark("browser_speech_start");
      }
      browserSpeechActive = true;
      if (browserSyncEnabled) console.log("BROWSER_STT_SYNC: speech_start");
    };

    browserRec.onspeechend = () => {
      const ts = Math.round(performance.now());
      if (debugBrowserEventsOnly) dbgScheduleEnd(ts);
      else {
        mark("browser_speech_end");
      }
      browserSpeechActive = false;
      if (browserSyncEnabled) {
        console.log("BROWSER_STT_SYNC: speech_end -> flush");
        finalizeUtteranceAndSend("browser_speech_end");
      }
    };

    // Algunos browsers son más confiables con "sound/audio end" que con "speech end".
    browserRec.onsoundstart = () => {
      if (debugBrowserEventsOnly) {
        const ts = Math.round(performance.now());
        // fallback: algunos browsers disparan sound/audio start pero no speechstart
        dbgEmitStart(ts);
      }
    };

    browserRec.onsoundend = () => {
      const ts = Math.round(performance.now());
      if (debugBrowserEventsOnly) dbgScheduleEnd(ts);
      else {
        mark("browser_sound_end");
      }
      if (browserSyncEnabled) {
        console.log("BROWSER_STT_SYNC: sound_end -> schedule flush");
        scheduleSyncFinalize("browser_sound_end", 150);
      }
    };

    browserRec.onaudiostart = () => {
      if (debugBrowserEventsOnly) {
        const ts = Math.round(performance.now());
        // fallback: algunos browsers disparan sound/audio start pero no speechstart
        dbgEmitStart(ts);
      }
    };

    browserRec.onaudioend = () => {
      const ts = Math.round(performance.now());
      if (debugBrowserEventsOnly) dbgScheduleEnd(ts);
      else {
        mark("browser_audio_end");
      }
      if (browserSyncEnabled) {
        console.log("BROWSER_STT_SYNC: audio_end -> schedule flush");
        scheduleSyncFinalize("browser_audio_end", 150);
      }
    };

    browserRec.onresult = (event) => {
      if (debugBrowserEventsOnly) {
        // En este modo usamos onresult como señal real:
        // - START: primer resultado no vacío (interim o final)
        // - END: 700ms sin nuevos resultados (silencio)
        let finalText = "";
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const r = event.results[i];
          const t = (r[0]?.transcript || "").trim();
          if (!t) continue;
          if (r?.isFinal) finalText += (finalText ? " " : "") + t;
          else interimText += (interimText ? " " : "") + t;
        }
        const ts = Math.round(performance.now());
        if (finalText || interimText) {
          if (!dbgUtteranceActive) dbgEmitStart(ts);
          dbgLastResultTs = ts;
          if (interimText) dbgInterimText = interimText;
          if (finalText) dbgFinalText = finalText;
          dbgKickInactivityTimer();
        }
        return;
      }
      try {
        let finalText = "";
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const r = event.results[i];
          const t = (r[0]?.transcript || "").trim();
          if (!t) continue;
          if (r.isFinal) finalText += (finalText ? " " : "") + t;
          else interimText += (interimText ? " " : "") + t;
        }
        const ts = Math.round(performance.now());
        // Dedup/throttle para que el debug sea legible.
        // Interim puede repetirse varias veces mientras el motor "se estabiliza".
        if (interimText) {
          const changed = interimText !== lastBrowserInterim;
          const throttleOk = (ts - lastBrowserInterimAt) >= 250;
          if (changed || throttleOk) {
            console.log(`BROWSER_STT_INTERIM @${ts}ms:`, interimText);
            lastBrowserInterim = interimText;
            lastBrowserInterimAt = ts;
          }
        }
        if (finalText && finalText !== lastBrowserFinal) {
          console.log(`BROWSER_STT_FINAL @${ts}ms:`, finalText);
          lastBrowserFinal = finalText;
          // En modo sync: usar FINAL como señal de cierre (fallback si onspeechend no se dispara).
          if (browserSyncEnabled) {
            scheduleSyncFinalize("browser_final", 200);
          }
        }
      } catch (e) {
        console.warn("BROWSER_STT: error procesando result", e);
      }
    };

    browserRec.onerror = (e) => {
      // Normalmente e.error trae: 'no-speech', 'aborted', 'network', 'not-allowed', 'audio-capture', etc.
      if (debugBrowserEventsOnly) {
        const ts = Math.round(performance.now());
        // En debug puro, cerramos la frase si estaba activa (sin texto)
        dbgEmitEnd(ts, "");
        return;
      }
      const ts = Math.round(performance.now());
      console.warn("BROWSER_STT: error", {
        at: `${ts}ms`,
        error: e?.error,
        message: e?.message,
        type: e?.type,
        timeStamp: e?.timeStamp,
      });
      // En modo sync, si el motor falla y tenemos audio acumulado, flusheamos igual para no quedarnos colgados.
      if (browserSyncEnabled) {
        scheduleSyncFinalize(`browser_error:${e?.error || "unknown"}`, 0);
      }
    };

    browserRec.onend = () => {
      if (!debugBrowserEventsOnly) {
        mark("browser_stt_end");
        console.log("BROWSER_STT: ended");
      }
      // Si el motor terminó y estábamos en "speech_active", cortamos la frase para no quedar colgados.
      if (browserSyncEnabled && (browserSpeechActive || audioInUtterance)) {
        browserSpeechActive = false;
        scheduleSyncFinalize("browser_rec_end", 0);
      }
      if (debugBrowserEventsOnly && dbgUtteranceActive) {
        const ts = Math.round(performance.now());
        dbgScheduleEnd(ts);
      }
      const shouldRestart = browserSttEnabled && !browserSttStopping && (listenStatus.textContent === "listening");
      browserRec = null;
      if (shouldRestart) {
        // Algunos browsers cortan por silencio; reintenta mientras seguimos en listening.
        setTimeout(() => startBrowserSttDebug(), 250);
      }
    };

    browserRec.start();
  } catch (e) {
    console.warn("BROWSER_STT: no se pudo iniciar", e);
    browserRec = null;
  }
}

function stopBrowserSttDebug() {
  browserSttStopping = true;
  browserSttEnabled = false;
  try {
    browserRec?.stop();
  } catch {}
}

function forceBrowserSttFinalizeNow(reason = "audio_stop") {
  // Intenta reducir la latencia al FINAL del STT del navegador.
  // Nota: no es 100% controlable; depende del motor del navegador.
  if (!browserRec) return;
  try {
    const ts = Math.round(performance.now());
    console.log(`BROWSER_STT_FORCE_STOP @${ts}ms (${reason})`);
    // Importante: NO cambiamos browserSttStopping acá, porque queremos que onend reinicie
    // automáticamente mientras estemos en "listening".
    browserRec.stop();
  } catch (e) {
    console.warn("BROWSER_STT_FORCE_STOP failed:", e);
  }
}

function cleanup() {
  try { processorNode?.disconnect(); } catch {}
  try { sourceNode?.disconnect(); } catch {}
  try { if (processorNode?.port) processorNode.port.onmessage = null; } catch {}
  try { if (audioCtx && audioCtx.state !== "closed") audioCtx.close(); } catch {}
  try { stream?.getTracks()?.forEach(t => t.stop()); } catch {}
  audioCtx = null;
  sourceNode = null;
  processorNode = null;
  stream = null;
  audioInUtterance = false;
  utteranceChunks = [];
  utteranceBytes = 0;
}

function pcm16ToWavBlob(pcmU8, sampleRate = 16000) {
  // pcmU8: Uint8Array de PCM16 mono LE
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = pcmU8.byteLength;

  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  let p = 0;

  function writeStr(s) {
    for (let i = 0; i < s.length; i++) view.setUint8(p++, s.charCodeAt(i));
  }

  writeStr("RIFF");
  view.setUint32(p, 36 + dataSize, true); p += 4;
  writeStr("WAVE");
  writeStr("fmt ");
  view.setUint32(p, 16, true); p += 4;          // PCM header size
  view.setUint16(p, 1, true); p += 2;           // PCM format
  view.setUint16(p, numChannels, true); p += 2;
  view.setUint32(p, sampleRate, true); p += 4;
  view.setUint32(p, byteRate, true); p += 4;
  view.setUint16(p, blockAlign, true); p += 2;
  view.setUint16(p, bitsPerSample, true); p += 2;
  writeStr("data");
  view.setUint32(p, dataSize, true); p += 4;

  new Uint8Array(buffer, 44).set(pcmU8);
  return new Blob([buffer], { type: "audio/wav" });
}

function concatChunks(chunks, totalBytes) {
  const out = new Uint8Array(totalBytes);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.byteLength;
  }
  return out;
}

async function ensureMicPermission() {
  const s = await navigator.mediaDevices.getUserMedia({ audio: true });
  s.getTracks().forEach((t) => t.stop());
}

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

function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0, offset = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

async function checkBackend() {
  try {
    const r = await fetch("/api/health");
    backendStatus.textContent = r.ok ? "ok" : `error ${r.status}`;
  } catch (e) {
    backendStatus.textContent = "no conectado";
  }
}

function appendLine(who, text) {
  const p = document.createElement("p");
  p.innerHTML = `<b>${who}:</b> ${text}`;
  transcriptDiv.appendChild(p);
  while (transcriptDiv.childNodes.length > 50) {
    transcriptDiv.removeChild(transcriptDiv.firstChild);
  }
}

async function start() {
  btnStart.disabled = true;
  btnStop.disabled = false;
  listenStatus.textContent = "starting";

  await checkBackend();

  // Modo mínimo: SOLO eventos del STT del navegador (sin WS / sin audio)
  if (debugBrowserEventsOnly) {
    wsStatus.textContent = "n/a";
    listenStatus.textContent = "listening";
    dbgResetUtterance();
    console.clear?.();
    console.log("DEBUG: browser_events");
    console.log('Formato: STT_START: <ms>  |  STT_END: <ms>, "<texto_final>"');
    startBrowserSttDebug();
    return;
  }

  // STT del navegador solo para comparar (debug). No afecta el backend.
  startBrowserSttDebug();

  // WS (mismo host:port de Vite; proxy /ws -> backend)
  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const wsHost = location.hostname === "localhost" ? "127.0.0.1" : location.hostname;
  const wsHostPort = location.port ? `${wsHost}:${location.port}` : wsHost;
  ws = new WebSocket(`${wsProto}://${wsHostPort}/ws/audio`);

  ws.onopen = async () => {
    wsStatus.textContent = "conectado";
    listenStatus.textContent = "listening";
    mark("interaction_start");
    ws.send(JSON.stringify({ type: "mark", label: "interaction_start", ts: performance.now() }));
    if (browserSyncEnabled) {
      console.log("BROWSER_STT_SYNC: ENABLED (captura PCM por getUserMedia; flush por onspeechend)");
    }

    const constraints = {
      audio: {
        deviceId: micSelect.value ? { exact: micSelect.value } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
        channelCount: 1,
      }
    };
    stream = await navigator.mediaDevices.getUserMedia(constraints);

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    // Worklet dedicado para STT-only (más permisivo que el usado por el avatar)
    await audioCtx.audioWorklet.addModule("stt-processor.js");

    sourceNode = audioCtx.createMediaStreamSource(stream);
    processorNode = new AudioWorkletNode(audioCtx, "pcm-processor-stt");

    processorNode.port.onmessage = (event) => {
      if (event.data.type === "audio") {
        const pcm16 = floatTo16BitPCM(event.data.data);
        if (ws?.readyState === WebSocket.OPEN) {
          if (browserSyncEnabled) {
            // Acumular siempre pre-roll. Solo guardamos "frase" cuando SpeechRecognition indica habla.
            pushPreRoll(pcm16);
            if (browserSpeechActive) {
              beginUtteranceIfNeeded();
              utteranceChunks.push(pcm16);
              utteranceBytes += pcm16.byteLength;
            }
          } else {
            if (!audioInUtterance) {
              audioInUtterance = true;
              mark("audio_start");
              ws.send(JSON.stringify({ type: "mark", label: "audio_start", ts: performance.now() }));
            }
            // Guardar para debug/reproducción local
            utteranceChunks.push(pcm16);
            utteranceBytes += pcm16.byteLength;
            ws.send(pcm16);
          }
        }
      } else if (event.data.type === "end_of_utterance") {
        // Si estamos en modo sync con Browser STT, ignoramos el VAD del worklet para no duplicar flush.
        if (browserSyncEnabled) return;
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(new Uint8Array(0));
          mark("audio_stop");
          ws.send(JSON.stringify({ type: "mark", label: "audio_stop", ts: performance.now() }));
          mark("waiting_response");
          ws.send(JSON.stringify({ type: "mark", label: "waiting_response", ts: performance.now() }));
          audioInUtterance = false;

          // Debug: forzar cierre de la hipótesis actual del STT del navegador para que emita FINAL antes
          forceBrowserSttFinalizeNow("audio_stop");

          const pcmAll = concatChunks(utteranceChunks, utteranceBytes);
          buildWavDebugFromPcm(pcmAll);
          resetUtteranceBuffers();
        }
      }
    };

    sourceNode.connect(processorNode);
  };

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      mark("response_received");
      ws.send(JSON.stringify({ type: "mark", label: "response_received", ts: performance.now() }));

      if (msg.text) appendLine("Usuario", msg.text);
      if (msg.respuesta) {
        const texto = msg.respuesta?.respuesta || msg.respuesta;
        appendLine("Sistema", texto);
      }
      if (msg.error) appendLine("Error", msg.error);
    } catch (e) {
      console.warn("Mensaje WS no JSON:", evt.data);
    }
  };

  ws.onerror = () => {
    wsStatus.textContent = "error";
    listenStatus.textContent = "error";
  };

  ws.onclose = () => {
    wsStatus.textContent = "cerrado";
    listenStatus.textContent = "idle";
    stopBrowserSttDebug();
    cleanup();
    btnStart.disabled = false;
    btnStop.disabled = true;
  };
}

function stop() {
  listenStatus.textContent = "stopping";
  stopBrowserSttDebug();
  if (debugBrowserEventsOnly) {
    listenStatus.textContent = "idle";
    btnStart.disabled = false;
    btnStop.disabled = true;
    return;
  }
  try { ws?.close(); } catch {}
  ws = null;
}

btnStart.addEventListener("click", start);
btnStop.addEventListener("click", stop);

// Init
(async () => {
  await checkBackend();
  try {
    await ensureMicPermission();
  } catch {}
  await populateMicSelect();
})();

