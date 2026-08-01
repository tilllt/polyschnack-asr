"""APIRouter for /api/recordings and /api/stats.

Each endpoint is thin: parse the incoming request, delegate to ``crud`` or
``service``, then shape the outgoing response dict.  No raw SQL here.
"""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
import hashlib
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from ..config import settings
from ..crud import (
    create_recording,
    delete_recording,
    get_recording,
    get_recording_by_uid,
    get_stats,
    list_recordings,
)
from ..db import get_session
from ..models import Recording
from ..permissions import ensure_access
from ..queue import QueueError, QueueFullError, queue_manager
from ..service import to_srt, to_txt, to_vtt, trim_audio
from ..whatsapp import parse_whatsapp

router = APIRouter(prefix="/api")

log = __import__("logging").getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user(request: Request) -> int | None:
    """Return current user_id from session, or None if anonymous or OIDC disabled.

    A ``None`` return means the recording is public (shared space).
    """
    if not settings.OIDC_ENABLED:
        return None
    return request.session.get("user_id")  # None = anonymous → shared space


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUDIO_MIME_FALLBACK = "audio/mpeg"

# Formats the browser can decode natively → WaveSurfer works
_BROWSER_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm", ".opus", ".aac"}


def _recording_to_dict(rec: Recording, access_level: Optional[str] = None) -> Dict[str, Any]:
    """Serialise a Recording row to the canonical API response shape."""
    uid = rec.uid or str(rec.id)  # fallback for legacy rows without uid
    return {
        "id": rec.id,
        "uid": uid,
        "original_name": rec.original_name,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "duration_s": rec.duration_s,
        "status": rec.status,
        "text": rec.text,
        "error": rec.error,
        "processing_ms": rec.processing_ms,
        "progress_pct": rec.progress_pct,
        "created_at": rec.created_at.isoformat(),
        "language": rec.language,
        "segments": rec.segments,
        "audio_url": f"/api/recordings/{uid}/audio",
        "download_url": f"/api/recordings/{uid}/download",
        # WhatsApp / batch fields
        "batch_id": rec.batch_id,
        "recorded_at": rec.recorded_at.isoformat() if rec.recorded_at else None,
        "source": rec.source,
        "enable_vad": rec.enable_vad,
        "enable_diarize": rec.enable_diarize,
        "enable_streaming": rec.enable_streaming,
        "enable_noise_reduce": rec.enable_noise_reduce,
        "enable_enhance": rec.enable_enhance,
        "waveform_peaks": rec.waveform_peaks,
        "user_id": rec.user_id,
        "access_level": access_level,
    }


def _guess_mime(stored_path: str, stored_mime: str) -> str:
    """Return a usable audio MIME type for *stored_path*.

    Falls back to *_AUDIO_MIME_FALLBACK* when guessing fails.
    """
    if stored_mime and stored_mime != "application/octet-stream":
        return stored_mime
    guessed, _ = mimetypes.guess_type(stored_path)
    return guessed or _AUDIO_MIME_FALLBACK


def _convert_to_wav_if_needed(raw: bytes, original_name: str) -> tuple[bytes, str, str | None]:
    """Convert any audio format to 16kHz 16bit mono WAV via ffmpeg.

    Returns (audio_bytes, final_extension, conversion_note).
    Always converts — WebM/Opus from mic recordings need it for the ASR
    service, and a uniform WAV store avoids surprises.
    If conversion fails, raises HTTPException.
    """
    ext = Path(original_name).suffix.lower()

    # Try ffmpeg conversion
    log.info("Converting %s to WAV", original_name)
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin",
                "-i", "pipe:0",
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                "-f", "wav",
                "pipe:1",
            ],
            input=raw,
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise HTTPException(
                status_code=400,
                detail=f"Konnte {original_name} nicht konvertieren: {err}",
            )
        out = proc.stdout
        if not out:
            raise HTTPException(
                status_code=400,
                detail=f"Konnte {original_name} nicht konvertieren: leere Ausgabe",
            )
        log.info("Converted %s: %d → %d bytes", original_name, len(raw), len(out))
        note = f"(konvertiert von {ext or 'unbekannt'} nach WAV)"
        return out, ".wav", note
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=400,
            detail=f"Konvertierung von {original_name} abgebrochen (länger als 120s)",
        )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/recordings", status_code=201)
async def upload_recording(
    request: Request,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Accept a multipart audio upload, persist it."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")

    # Limit upload size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"file too large (max {settings.MAX_UPLOAD_SIZE_MB} MB)")
    await file.close()

    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    # Compute content hash for duplicate detection
    content_hash = hashlib.blake2b(raw, digest_size=16).hexdigest()
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()

    if existing and not (request.query_params.get("force") == "true"):
        return {
            "duplicate": True,
            "existing_id": existing.id,
            "recording": _recording_to_dict(existing),
        }

    # Convert non-browser formats to WAV
    audio_data, new_ext, conv_note = _convert_to_wav_if_needed(raw, file.filename)

    stored = settings.AUDIO_DIR / f"{uuid.uuid4().hex}{new_ext}"
    stored.write_bytes(audio_data)

    recorded_at, source = parse_whatsapp(file.filename)

    # Estimate duration from file size (rough, for ETA display).
    # 16kHz/16bit = 32000 bytes/sec; compressed audio is smaller,
    # so this is a conservative overestimate.
    est_duration_s = len(audio_data) / 16000 if new_ext == ".wav" else len(raw) / 8000

    # Append conversion note to original name so the user knows
    display_name = file.filename
    if conv_note:
        display_name = f"{file.filename} {conv_note}"

    rec = create_recording(
        session,
        original_name=display_name,
        stored_path=str(stored),
        mime="audio/wav" if new_ext == ".wav" else (file.content_type or "application/octet-stream"),
        size_bytes=len(audio_data),
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        duration_s=est_duration_s,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        content_hash=content_hash,
        user_id=_current_user(request),
    )
    return _recording_to_dict(rec)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


@router.get("/recordings")
def list_recordings_endpoint(
    q: Optional[str] = None,
    request: Request = None,
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Return all recordings (newest first), optionally filtered by *q*."""
    rows = list_recordings(session, q=q, user_id=_current_user(request))
    return [_recording_to_dict(r) for r in rows]


@router.get("/recordings/{rid}")
def get_recording_endpoint(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Return a single recording dict including segments."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request) if settings.OIDC_ENABLED else None
    ensure_access(session, rec, uid, "read")
    d = _recording_to_dict(rec)
    # Debug: include word presence info without changing data
    segs = d.get("segments") or []
    d["_words_debug"] = {
        "total_segments": len(segs),
        "segs_with_words": sum(1 for s in segs if s.get("words") and len(s["words"]) > 0),
        "total_words": sum(len(s.get("words") or []) for s in segs),
    }
    return d


# ---------------------------------------------------------------------------
# Audio streaming
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/audio")
def get_audio(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Stream the stored audio file with Range request support."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request) if settings.OIDC_ENABLED else None
    ensure_access(session, rec, uid, "read")

    path = Path(rec.stored_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="audio file gone")

    mime = _guess_mime(rec.stored_path, rec.mime)
    return FileResponse(
        str(path),
        media_type=mime,
        filename=rec.original_name,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# Download (subtitle/transcript export)
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/download")
def download_transcript(
    rid: str,
    format: str = "txt",
    session: Session = Depends(get_session),
) -> Response:
    """Download the transcription as txt, srt, or vtt."""
    if format not in ("txt", "srt", "vtt"):
        raise HTTPException(status_code=400, detail="format must be txt, srt, or vtt")

    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    stem = Path(rec.original_name).stem
    disposition = f'attachment; filename="{stem}.{format}"'

    if format == "txt":
        content = to_txt(rec.text or "")
        media_type = "text/plain"
    elif format == "srt":
        content = to_srt(rec.segments or [])
        media_type = "application/x-subrip"
    else:  # vtt
        content = to_vtt(rec.segments or [])
        media_type = "text/vtt"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


# ---------------------------------------------------------------------------
# Transcribe (start manually)
# ---------------------------------------------------------------------------


@router.post("/recordings/{rid}/transcribe")
def transcribe_ep(
    rid: str,
    request: Request,
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
    backend: str = Form(""),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Queue a transcription for an uploaded recording (Task 6)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request) if settings.OIDC_ENABLED else None
    ensure_access(session, rec, uid, "full")

    # Update toggle values from the transcribe request (they may have changed since upload)
    rec.enable_vad = enable_vad
    rec.enable_diarize = enable_diarize
    rec.enable_streaming = enable_streaming
    rec.enable_noise_reduce = enable_noise_reduce
    rec.enable_enhance = enable_enhance
    session.add(rec)
    session.commit()

    backend = backend or settings.POLYSCHNACK_DEFAULT_BACKEND
    try:
        position = queue_manager.enqueue(int(rec.id), uid, backend)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": rid, "status": "queued", "position": position, "backend": backend}


# ---------------------------------------------------------------------------
# Re-transcribe
# ---------------------------------------------------------------------------


class RetranscribeParams(BaseModel):
    enable_vad: bool = False
    enable_diarize: bool = False
    enable_streaming: bool = False
    enable_noise_reduce: bool = True
    enable_enhance: str = "off"
    backend: str = ""


@router.post("/recordings/{rid}/retranscribe")
def retranscribe(
    rid: str,
    params: RetranscribeParams = RetranscribeParams(),
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Reset transcription state, update settings, and re-queue for processing."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    rec.enable_vad = params.enable_vad
    rec.enable_diarize = params.enable_diarize
    rec.enable_streaming = params.enable_streaming
    rec.enable_noise_reduce = params.enable_noise_reduce
    rec.enable_enhance = params.enable_enhance
    session.add(rec)
    session.commit()

    backend = params.backend or settings.POLYSCHNACK_DEFAULT_BACKEND
    try:
        position = queue_manager.enqueue(int(rec.id), uid, backend)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": rid, "status": "queued", "position": position, "backend": backend}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/recordings/{rid}")
def delete_recording_endpoint(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Delete the database row and the audio file from disk."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    rec = delete_recording(session, rec.id)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    path = Path(rec.stored_path)
    path.unlink(missing_ok=True)
    return {"deleted": rid}


# ---------------------------------------------------------------------------
# Crop / transcribe-range
# ---------------------------------------------------------------------------


@router.post("/recordings/{rid}/transcribe-range", status_code=201)
def transcribe_range(
    rid: str,
    start_sec: float,
    end_sec: float,
    request: Request = None,
    session: Session = Depends(get_session),
):
    """Crop audio to [start_sec, end_sec] and transcribe the segment as a new recording."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")

    audio_bytes = Path(rec.stored_path).read_bytes()
    trimmed = trim_audio(audio_bytes, start_sec, end_sec)

    stem = Path(rec.stored_path).stem
    parent = Path(rec.stored_path).parent
    crop_path = parent / f"{stem}_crop_{int(start_sec)}-{int(end_sec)}.wav"
    crop_path.write_bytes(trimmed)

    new_rec = create_recording(
        session,
        original_name=f"crop_{start_sec:.0f}s-{end_sec:.0f}s_{rec.original_name}",
        stored_path=str(crop_path),
        mime="audio/wav",
        size_bytes=len(trimmed),
        batch_id=rec.batch_id,
        enable_vad=rec.enable_vad,
        enable_diarize=rec.enable_diarize,
        user_id=uid,
    )
    return _recording_to_dict(new_rec)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def stats_endpoint(
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Aggregate counts and totals across all recordings."""
    uid = _current_user(request) if settings.OIDC_ENABLED else None
    return get_stats(session, user_id=uid)
