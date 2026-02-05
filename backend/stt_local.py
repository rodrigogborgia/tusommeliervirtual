import os
import threading
import logging

import numpy as np

logger = logging.getLogger("stt-local")

# Lazy singleton model (carga pesada)
_model = None
_lock = threading.Lock()


def _get_env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and str(v).strip() != "" else default


def get_local_whisper_model():
    """
    Inicializa y cachea faster-whisper WhisperModel.
    CPU-only friendly: compute_type=int8 por defecto.
    """
    global _model
    if _model is not None:
        return _model

    with _lock:
        if _model is not None:
            return _model

        from faster_whisper import WhisperModel

        model_name = _get_env("WHISPER_MODEL", "small")
        compute_type = _get_env("WHISPER_COMPUTE_TYPE", "int8")

        # device: cpu (sin NVIDIA)
        logger.info(f"Inicializando faster-whisper: model={model_name} device=cpu compute_type={compute_type}")
        _model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
        return _model


def transcribe_pcm16_phrase(pcm_bytes: bytes) -> str:
    """
    Transcribe una frase PCM16 mono 16kHz (little-endian) a texto usando faster-whisper.
    Retorna string (puede ser vacía).
    """
    if not pcm_bytes:
        return ""

    audio_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    if audio_i16.size == 0:
        return ""
    audio_f32 = audio_i16.astype(np.float32) / 32768.0

    language = _get_env("STT_LANGUAGE", "es")
    try:
        beam_size = int(_get_env("WHISPER_BEAM_SIZE", "1"))
    except Exception:
        beam_size = 1

    model = get_local_whisper_model()

    # Nota: sin vad_filter porque ya segmentamos en el server + worklet.
    segments, info = model.transcribe(
        audio_f32,
        language=language,
        beam_size=beam_size,
        temperature=0.0,
    )

    text_parts = []
    for seg in segments:
        if seg.text:
            text_parts.append(seg.text)

    out = " ".join(t.strip() for t in text_parts if t and t.strip()).strip()
    logger.info(f"faster-whisper: lang={language} beam={beam_size} dur={getattr(info, 'duration', None)} text_len={len(out)}")
    return out

