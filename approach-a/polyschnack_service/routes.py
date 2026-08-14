"""FastAPI routes: OpenAI-compatible transcription + SSE streaming + async jobs."""
from __future__ import annotations
import asyncio
import datetime
import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from .audio import load_audio, reduce_noise
from .config import (
    CPU_INFO,
    DEFAULT_MODEL,
    MODEL_CONFIGS,
    NOISE_REDUCE,
    TARGET_SR,
    USE_GPU,
    logger,
)
from .core import clean_text, stream_wav, transcribe_wav
from .model import loaded_models

router = APIRouter()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _resolve_model(model: Optional[str]) -> str:
    raw = (model or DEFAULT_MODEL)
    if raw in MODEL_CONFIGS:
        return raw
    lowered = raw.lower()
    for k in MODEL_CONFIGS:
        if k.lower() == lowered:
            return k
    logger.warning("Unknown model %r, using %s", raw, DEFAULT_MODEL)
    return DEFAULT_MODEL


def _device() -> str:
    if USE_GPU == "false":
        return "cpu"
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" in ort.get_available_providers():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _fmt_srt_time(seconds: float) -> str:
    d = datetime.timedelta(seconds=max(0.0, seconds))
    s = str(d)
    if "." in s:
        a, b = s.split(".")
        ms = b[:3].ljust(3, "0")
    else:
        a, ms = s, "000"
    if a.count(":") == 1:
        a = "0:" + a
    return f"{a},{ms}"


def _segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for i, seg in enumerate(segments, 1):
        text = seg["segment"].strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(seg['start'])} --> {_fmt_srt_time(seg['end'])}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _segments_to_vtt(segments: List[Dict[str, Any]]) -> str:
    out = ["WEBVTT", ""]
    for seg in segments:
        text = seg["segment"].strip()
        if not text:
            continue
        s = _fmt_srt_time(seg["start"]).replace(",", ".")
        e = _fmt_srt_time(seg["end"]).replace(",", ".")
        out.extend([f"{s} --> {e}", text, ""])
    return "\n".join(out)


async def _read_upload(file: UploadFile) -> bytes:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    raw = await file.read()
    await file.close()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    return raw


def _decode(raw: bytes):
    try:
        wav = load_audio(raw)
    except Exception as exc:
        logger.exception("audio decode failed")
        raise HTTPException(status_code=415, detail=f"audio decode failed: {exc}") from exc
    if wav.size / TARGET_SR <= 0:
        raise HTTPException(status_code=400, detail="Empty audio")
    return wav


# ---------------------------------------------------------------------------
# Health / metrics
# ---------------------------------------------------------------------------


def _vram_free_gb():
    """Free VRAM in GB via nvidia-smi inside the CUDA container, or None."""
    import shutil
    import subprocess

    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        free_mb = float(out.stdout.strip().split(",")[0])
        return round(free_mb / 1024, 1)
    except Exception:
        return None


@router.get("/health")
def health():
    from .config import CHUNK_SECONDS, CHUNK_OVERLAP_SECONDS, MAX_BATCH_SIZE, MAX_WINDOWS_IN_FLIGHT

    return {
        "status": "ok",
        "model": DEFAULT_MODEL,
        "device": _device(),
        "models": list(MODEL_CONFIGS.keys()),
        "loaded": loaded_models(),
        "cpu": CPU_INFO,
        "resources": {"vram_free_gb": _vram_free_gb()},
        # Long-Audio-Profil — die Webapp nutzt das für die VRAM-Prognose
        # (sicherer Batch-Betrieb: VRAM-Bedarf skaliert mit der Fenstergröße,
        # nicht mit der Dateilänge).
        "asr": {
            "chunk_seconds": CHUNK_SECONDS,
            "chunk_overlap_seconds": CHUNK_OVERLAP_SECONDS,
            "max_batch_size": MAX_BATCH_SIZE,
            "max_windows_in_flight": MAX_WINDOWS_IN_FLIGHT,
        },
    }


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/metrics")
def metrics(request: Request):
    m = request.app.state.metrics
    jobs = request.app.state.jobs
    return m.snapshot(queue_depth=jobs.queue_depth)


# ---------------------------------------------------------------------------
# Core OpenAI-compatible transcribe
# ---------------------------------------------------------------------------
@router.post("/v1/audio/transcriptions")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
    response_format: str = Form("json"),
    timestamp_granularities: Optional[str] = Form(None),
    noise_reduce: Optional[bool] = Form(None),
):
    model_name = _resolve_model(model)
    raw = await _read_upload(file)

    t0 = time.perf_counter()
    ok = True
    try:
        wav = _decode(raw)
        # Noise reduction (per-request override, else env default)
        if noise_reduce if noise_reduce is not None else NOISE_REDUCE:
            wav = reduce_noise(wav)
        out = await transcribe_wav(request.app.state.worker, wav, model_name)
    except HTTPException:
        ok = False
        raise
    except Exception:
        ok = False
        raise
    finally:
        request.app.state.metrics.record((time.perf_counter() - t0) * 1000, ok=ok)

    segments = out["segments"]
    full_text = out["text"]
    fmt = (response_format or "json").lower()
    if fmt == "text":
        return PlainTextResponse(full_text)
    if fmt == "srt":
        return PlainTextResponse(_segments_to_srt(segments))
    if fmt == "vtt":
        return PlainTextResponse(_segments_to_vtt(segments))
    if fmt == "verbose_json":
        return JSONResponse({
            "task": "transcribe",
            "language": "auto",
            "duration": out["duration"],
            "text": full_text,
            "segments": [
                {
                    "id": i, "seek": 0,
                    "start": s["start"], "end": s["end"], "text": s["segment"],
                    "tokens": [], "words": s.get("words", []), "temperature": 0.0, "avg_logprob": 0.0,
                    "compression_ratio": 0.0, "no_speech_prob": 0.0,
                }
                for i, s in enumerate(segments)
            ],
            "words": out["words"] if (timestamp_granularities and "word" in timestamp_granularities) else None,
        })
    return JSONResponse({"text": full_text})


# ---------------------------------------------------------------------------
# SSE streaming: one event per VAD chunk as it finishes
# ---------------------------------------------------------------------------
@router.post("/v1/audio/transcriptions/stream")
async def transcribe_stream(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
    noise_reduce: Optional[bool] = Form(None),
):
    model_name = _resolve_model(model)
    raw = await _read_upload(file)
    wav = _decode(raw)
    if noise_reduce if noise_reduce is not None else NOISE_REDUCE:
        wav = reduce_noise(wav)
    worker = request.app.state.worker

    async def event_gen():
        t0 = time.perf_counter()
        ok = True
        try:
            async for ev in stream_wav(worker, wav, model_name):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface to client as an SSE error event
            ok = False
            logger.exception("stream failed")
            yield f"data: {json.dumps({'error': str(exc), 'final': True})}\n\n"
        finally:
            request.app.state.metrics.record((time.perf_counter() - t0) * 1000, ok=ok)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Async jobs for large audio
# ---------------------------------------------------------------------------
@router.post("/v1/audio/transcriptions/async")
async def transcribe_async(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
):
    model_name = _resolve_model(model)
    raw = await _read_upload(file)
    job_id = uuid4().hex
    await request.app.state.jobs.submit(job_id, raw, model_name)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=202)


@router.get("/v1/audio/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.public()


# ---------------------------------------------------------------------------
# Batch endpoint (non-OpenAI) for high-throughput pipelines
# ---------------------------------------------------------------------------
@router.post("/v1/audio/transcriptions/batch")
async def transcribe_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    model: str = Form(DEFAULT_MODEL),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    model_name = _resolve_model(model)

    raws = []
    for f in files:
        raws.append(await f.read())
        await f.close()

    loop = asyncio.get_running_loop()
    pool = request.app.state.audio_pool
    wavs = await asyncio.gather(*(loop.run_in_executor(pool, load_audio, r) for r in raws))

    worker = request.app.state.worker
    results = await worker.submit_many(list(wavs), model_name)
    texts = [clean_text(getattr(r, "text", str(r))) for r in results]
    return {
        "results": [
            {"filename": f.filename, "text": t, "duration": w.size / TARGET_SR}
            for f, t, w in zip(files, texts, wavs)
        ],
        "batch_size": len(files),
    }
