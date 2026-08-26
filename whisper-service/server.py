#!/usr/bin/env python3
"""PolySchnack Whisper ASR-Service (faster-whisper large-v3).

OpenAI-kompatible API:
    POST /v1/audio/transcriptions  (multipart: file, language?, model?)
    GET  /health

Modell wird lazy geladen (beim ersten Request) — der Health-Check bleibt
ohne Modell sofort beantwortbar; ASR_MODEL/COMPUTE_TYPE per env.
GPU (CUDA) mit CPU-Fallback; Sprache je Request (de/en/None=auto).
"""
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile

MODEL_NAME = os.environ.get("ASR_MODEL", "large-v3")
COMPUTE_TYPE = os.environ.get("COMPUTE_TYPE", "int8_float16")
DOWNLOAD_ROOT = "/app/models"

_model = None
_model_device = "cpu"


def get_model():
    """Lazy: einmalig laden; CUDA wenn verfügbar, sonst CPU (int8)."""
    global _model, _model_device
    if _model is None:
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                _model_device = "cuda"
        except Exception:
            pass
        from faster_whisper import WhisperModel
        ct = COMPUTE_TYPE if _model_device == "cuda" else "int8"
        _model = WhisperModel(MODEL_NAME, device=_model_device,
                              compute_type=ct, download_root=DOWNLOAD_ROOT)
    return _model


app = FastAPI(title="PolySchnack Whisper", version="1.0")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "device": _model_device}


@app.get("/version")
def version():
    """Build-Version (Change 134): Git-Commit-SHA des laufenden Images."""
    import os

    commit = os.environ.get("GIT_SHA", "dev").strip() or "dev"
    return {"service": "whisper", "commit": commit, "image_tag": commit}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    model: str | None = Form(None),  # OpenAI-Kompatibilität (wird ignoriert)
    response_format: str = Form("json"),
):
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    data = await file.read()
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
        segments, info = get_model().transcribe(
            path, language=language or None, vad_filter=True)
        text = "".join(s.text for s in segments).strip()
        if response_format == "verbose_json":
            segs = [{"start": round(s.start, 3), "end": round(s.end, 3),
                     "text": s.text} for s in segments]
            return {"text": text, "language": info.language,
                    "duration": round(info.duration, 3), "segments": segs}
        return {"text": text, "language": info.language}
    finally:
        if path:
            os.unlink(path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
