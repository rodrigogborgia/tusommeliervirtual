import io
import struct
import wave
import logging
import re
import os

logger = logging.getLogger("audio-utils")

# --- Constantes ---
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 2000
SILENCE_DURATION = 0.8
MAX_PHRASE_SECONDS = 2.0

# Gating extra para evitar "alucinaciones" de Whisper con audio casi silencioso.
# Modo "estricto" (minimiza falsos positivos):
# - Requiere un poco más de duración.
# - Requiere más energía (RMS/pico) para evitar transcripciones sobre hiss/silencio.
_MIN_PHRASE_SECONDS_DEFAULT = 0.35
try:
    MIN_PHRASE_SECONDS_TO_TRANSCRIBE = float(os.getenv("STT_MIN_PHRASE_SECONDS", str(_MIN_PHRASE_SECONDS_DEFAULT)))
except Exception:
    MIN_PHRASE_SECONDS_TO_TRANSCRIBE = _MIN_PHRASE_SECONDS_DEFAULT
MIN_RMS_TO_TRANSCRIBE = 550.0  # RMS en int16 (0..~32767)
MIN_PEAK_TO_TRANSCRIBE = 1500  # pico absoluto en int16

# --- Funciones auxiliares ---
def is_chunk_silent(pcm_bytes: bytes, threshold: int = SILENCE_THRESHOLD) -> bool:
    """
    Determina si un bloque PCM16 es silencio.
    """
    count = len(pcm_bytes) // 2
    for i in range(count):
        sample = struct.unpack_from("<h", pcm_bytes, i * 2)[0]
        if abs(sample) > threshold:
            return False
    return True

def pcm_rms_int16(pcm_bytes: bytes) -> float:
    """
    RMS (root mean square) aproximado para PCM16 little-endian.
    Devuelve 0 si el buffer es inválido/vacío.
    """
    if not pcm_bytes:
        return 0.0
    count = len(pcm_bytes) // 2
    if count <= 0:
        return 0.0
    acc = 0.0
    for i in range(count):
        s = struct.unpack_from("<h", pcm_bytes, i * 2)[0]
        acc += float(s) * float(s)
    return (acc / count) ** 0.5

def pcm_peak_abs_int16(pcm_bytes: bytes) -> int:
    """
    Pico absoluto (max(|sample|)) para PCM16 little-endian.
    """
    if not pcm_bytes:
        return 0
    count = len(pcm_bytes) // 2
    peak = 0
    for i in range(count):
        s = struct.unpack_from("<h", pcm_bytes, i * 2)[0]
        a = abs(s)
        if a > peak:
            peak = a
    return peak

def should_transcribe_phrase(pcm_bytes: bytes) -> tuple[bool, dict]:
    """
    Decide si vale la pena mandar a Whisper la frase.
    Retorna (ok, metrics) donde metrics sirve para logging/debug.
    """
    duration_sec = len(pcm_bytes) / (SAMPLE_RATE * 2) if pcm_bytes else 0.0
    rms = pcm_rms_int16(pcm_bytes)
    peak = pcm_peak_abs_int16(pcm_bytes)
    metrics = {"duration_sec": duration_sec, "rms": rms, "peak": peak}

    if duration_sec < MIN_PHRASE_SECONDS_TO_TRANSCRIBE:
        return False, metrics
    if rms < MIN_RMS_TO_TRANSCRIBE and peak < MIN_PEAK_TO_TRANSCRIBE:
        return False, metrics
    return True, metrics

def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> io.BytesIO:
    """
    Convierte bytes PCM16 en un archivo WAV en memoria.
    """
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    buf.name = "chunk.wav"
    return buf

# --- Clase para segmentar frases ---
class AudioBuffer:
    """
    Acumula chunks de audio y devuelve frases completas.
    Usa silencio prolongado o tamaño máximo como criterio de corte.
    """
    def __init__(self, silence_threshold=SILENCE_THRESHOLD, silence_duration=SILENCE_DURATION):
        self.buffer = []
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.silence_time = 0.0

    def add_chunk(self, pcm_bytes: bytes):
        """
        Acumula audio y devuelve una frase cuando se detecta silencio prolongado
        o se alcanza el tamaño máximo.
        """
        if pcm_bytes:
            self.buffer.append(pcm_bytes)

            # Detectar silencio en este chunk
            if is_chunk_silent(pcm_bytes, self.silence_threshold):
                # duración de este chunk en segundos
                chunk_seconds = len(pcm_bytes) / (SAMPLE_RATE * 2)
                self.silence_time += chunk_seconds
            else:
                self.silence_time = 0.0

            # Condición de corte: silencio prolongado o tamaño máximo
            total_len = sum(len(b) for b in self.buffer)
            total_seconds = total_len / (SAMPLE_RATE * 2)

            if self.silence_time >= self.silence_duration or total_seconds >= MAX_PHRASE_SECONDS:
                phrase = b"".join(self.buffer)
                self.buffer.clear()
                self.silence_time = 0.0
                return phrase
        return None

    def flush(self):
        phrase = b''.join(self.buffer)
        self.buffer.clear()
        if phrase:
            duration_sec = len(phrase) / (16000 * 2)  # suponiendo 16kHz, 16-bit PCM
            logger.info(f"AudioBuffer flush: {len(phrase)} bytes (~{duration_sec:.2f} sec)")
        return phrase

# --- Filtro de transcripciones ---
def is_valid_transcription(text: str) -> bool:
    """
    Filtra transcripciones irrelevantes o sospechosas antes de pasarlas al LLM.
    """
    if not text or len(text.strip()) < 3:
        return False
    blacklist = ["Amara.org", "subtítulos realizados", "undefined", "test"]
    lowered = text.lower()

    # Filtro anti "publicidad/urls" (Whisper suele alucinar urls con ruido/silencio).
    if re.search(r"(https?://|www\.|\.(com|net|org|io|cl|ar|mx|es|uy|br)\b)", lowered):
        return False

    return not any(bad.lower() in lowered for bad in blacklist)
