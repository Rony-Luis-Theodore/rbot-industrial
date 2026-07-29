"""
=============================================================================
R-Bot — Voz: transcripción de audio (fallback industrial)
=============================================================================

Endpoint:
    POST /api/v1/voice/transcribe  (multipart: audio)
    GET  /api/v1/voice/status

Backends (en orden):
    1. faster-whisper si está instalado (recomendado en CPU)
    2. openai-whisper si está instalado
    3. Error 503 con instrucciones de instalación
=============================================================================
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_whisper_model = None
_whisper_backend: Optional[str] = None
_whisper_error: Optional[str] = None


class TranscribeResponse(BaseModel):
    text: str
    backend: str
    language: str = "es"


class VoiceStatusResponse(BaseModel):
    ready: bool
    backend: Optional[str] = None
    model: str
    detail: str


def _model_name() -> str:
    return os.getenv("ML_WHISPER_MODEL", "base")


def _load_whisper():
    """Carga perezosa de Whisper (CPU)."""
    global _whisper_model, _whisper_backend, _whisper_error
    if _whisper_model is not None:
        return _whisper_model, _whisper_backend
    if _whisper_error and _whisper_backend is None and _whisper_model is None:
        # Reintentar si falló antes (p.ej. dependencia instalada después)
        pass

    model_name = _model_name()

    try:
        from faster_whisper import WhisperModel  # type: ignore

        _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        _whisper_backend = "faster-whisper"
        _whisper_error = None
        logger.info("Whisper cargado: faster-whisper/%s", model_name)
        return _whisper_model, _whisper_backend
    except Exception as exc:  # noqa: BLE001
        logger.info("faster-whisper no disponible: %s", exc)
        _whisper_error = str(exc)

    try:
        import whisper  # type: ignore

        _whisper_model = whisper.load_model(model_name)
        _whisper_backend = "openai-whisper"
        _whisper_error = None
        logger.info("Whisper cargado: openai-whisper/%s", model_name)
        return _whisper_model, _whisper_backend
    except Exception as exc:  # noqa: BLE001
        logger.info("openai-whisper no disponible: %s", exc)
        _whisper_error = str(exc)

    return None, None


def _to_wav_16k_mono(src: str) -> str:
    """
    Normaliza webm/ogg/mp4/wav → WAV PCM 16 kHz mono.
    MediaRecorder (Firefox/Chrome) suele mandar webm/ogg; Whisper/VAD
    fallan menos con WAV lineal.
    """
    try:
        import av  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("PyAV no disponible, se usa archivo original: %s", exc)
        return src

    dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
    os.close(dst_fd)

    try:
        container = av.open(src)
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise RuntimeError("Sin pista de audio en el archivo")

        resampler = av.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=16000,
        )
        frames_out = []
        for frame in container.decode(stream):
            converted = resampler.resample(frame)
            if converted is None:
                continue
            if isinstance(converted, list):
                frames_out.extend(converted)
            else:
                frames_out.append(converted)
        # Flush
        flushed = resampler.resample(None)
        if flushed:
            if isinstance(flushed, list):
                frames_out.extend(flushed)
            else:
                frames_out.append(flushed)

        if not frames_out:
            raise RuntimeError("Audio vacío tras decodificar")

        out = av.open(dst_path, mode="w", format="wav")
        out_stream = out.add_stream("pcm_s16le", rate=16000)
        out_stream.layout = "mono"
        for frame in frames_out:
            frame.pts = None
            for packet in out_stream.encode(frame):
                out.mux(packet)
        for packet in out_stream.encode(None):
            out.mux(packet)
        out.close()
        container.close()
        return dst_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Conversión a WAV falló (%s); se usa original", exc)
        try:
            os.unlink(dst_path)
        except OSError:
            pass
        return src


@router.get(
    "/status",
    response_model=VoiceStatusResponse,
    summary="Estado del motor de voz (Whisper)",
)
async def voice_status() -> VoiceStatusResponse:
    model, backend = _load_whisper()
    if model is None:
        return VoiceStatusResponse(
            ready=False,
            backend=None,
            model=_model_name(),
            detail=(
                "Whisper no instalado. En el PC de la API: "
                "pip install --user faster-whisper  y reinicia uvicorn."
            ),
        )
    return VoiceStatusResponse(
        ready=True,
        backend=backend,
        model=_model_name(),
        detail=f"Listo ({backend})",
    )


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribir audio a texto (ES)",
)
async def transcribe_audio(audio: UploadFile = File(...)) -> TranscribeResponse:
    """
    Recibe un blob de audio (webm/wav/ogg) y devuelve texto en español.
    """
    model, backend = _load_whisper()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Whisper no instalado en el servidor. "
                "En la máquina de la API ejecuta: pip install --user faster-whisper "
                "y reinicia la API. En Firefox la voz usa este backend (no Web Speech)."
            ),
        )

    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    raw = await audio.read()
    if len(raw) < 200:
        raise HTTPException(status_code=400, detail="Audio vacío o demasiado corto")

    src_path = None
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            src_path = tmp.name

        wav_path = _to_wav_16k_mono(src_path)
        text = _run_transcribe(model, backend, wav_path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Transcripción falló")
        raise HTTPException(status_code=500, detail=f"Error al transcribir: {exc}") from exc
    finally:
        for p in {src_path, wav_path}:
            if not p:
                continue
            try:
                os.unlink(p)
            except OSError:
                pass

    text = (text or "").strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se detectó habla clara. Habla más cerca del mic, "
                "graba al menos 2–3 segundos y vuelve a intentar."
            ),
        )

    return TranscribeResponse(text=text, backend=backend or "unknown", language="es")


def _run_transcribe(model: Any, backend: Optional[str], path: str) -> str:
    if backend == "faster-whisper":
        # vad_filter=False: Firefox/webm a menudo se filtraba entero como "silencio"
        segments, _info = model.transcribe(
            path,
            language="es",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    result = model.transcribe(path, language="es", fp16=False)
    return (result.get("text") or "").strip()
