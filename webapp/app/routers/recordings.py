"""APIRouter for /api/recordings and /api/stats.

Each endpoint is thin: parse the incoming request, delegate to ``crud`` or
``service``, then shape the outgoing response dict.  No raw SQL here.
"""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlmodel import Session

from ..config import settings
from ..crud import (
    create_recording,
    delete_recording,
    get_recording,
    get_stats,
    list_recordings,
    set_processing,
)
from ..db import get_session
from ..models import Recording
from ..service import process_recording, to_srt, to_txt, to_vtt
from ..whatsapp import parse_whatsapp

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUDIO_MIME_FALLBACK = "audio/mpeg"


def _recording_to_dict(rec: Recording) -> Dict[str, Any]:
    """Serialise a Recording row to the canonical API response shape."""
    return {
        "id": rec.id,
        "original_name": rec.original_name,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "duration_s": rec.duration_s,
        "status": rec.status,
        "text": rec.text,
        "error": rec.error,
        "processing_ms": rec.processing_ms,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "language": rec.language,
        "segments": rec.segments,
        "audio_url": f"/api/recordings/{rec.id}/audio",
        "download_url": f"/api/recordings/{rec.id}/download",
        # WhatsApp / batch fields
        "batch_id": rec.batch_id,
        "recorded_at": rec.recorded_at.isoformat() if rec.recorded_at else None,
        "source": rec.source,
        "enable_vad": rec.enable_vad,
        "enable_diarize": rec.enable_diarize,
    }


def _guess_mime(stored_path: str, stored_mime: str) -> str:
    """Return a usable audio MIME type for *stored_path*.

    Falls back to *_AUDIO_MIME_FALLBACK* when guessing fails.
    """
    if stored_mime and stored_mime != "application/octet-stream":
        return stored_mime
    guessed, _ = mimetypes.guess_type(stored_path)
    return guessed or _AUDIO_MIME_FALLBACK


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/recordings", status_code=201)
async def upload_recording(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Accept a multipart audio upload, persist it, and kick off transcription."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")

    raw = await file.read()
    await file.close()

    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    ext = Path(file.filename).suffix or ".bin"
    stored = settings.AUDIO_DIR / f"{uuid.uuid4().hex}{ext}"
    stored.write_bytes(raw)

    recorded_at, source = parse_whatsapp(file.filename)

    rec = create_recording(
        session,
        original_name=file.filename,
        stored_path=str(stored),
        mime=file.content_type or "application/octet-stream",
        size_bytes=len(raw),
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
    )
    background.add_task(process_recording, rec.id)
    return _recording_to_dict(rec)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


@router.get("/recordings")
def list_recordings_endpoint(
    q: Optional[str] = None,
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Return all recordings (newest first), optionally filtered by *q*."""
    rows = list_recordings(session, q=q)
    return [_recording_to_dict(r) for r in rows]


@router.get("/recordings/{rid}")
def get_recording_endpoint(
    rid: int,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Return a single recording dict including segments."""
    rec = get_recording(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    return _recording_to_dict(rec)


# ---------------------------------------------------------------------------
# Audio streaming
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/audio")
def get_audio(
    rid: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Stream the stored audio file with Range request support."""
    rec = get_recording(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    path = Path(rec.stored_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="audio file gone")

    mime = _guess_mime(rec.stored_path, rec.mime)
    return FileResponse(str(path), media_type=mime, filename=rec.original_name)


# ---------------------------------------------------------------------------
# Download (subtitle/transcript export)
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/download")
def download_transcript(
    rid: int,
    format: str = "txt",
    session: Session = Depends(get_session),
) -> Response:
    """Download the transcription as txt, srt, or vtt."""
    if format not in ("txt", "srt", "vtt"):
        raise HTTPException(status_code=400, detail="format must be txt, srt, or vtt")

    rec = get_recording(session, rid)
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
# Re-transcribe
# ---------------------------------------------------------------------------


@router.post("/recordings/{rid}/retranscribe")
def retranscribe(
    rid: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Reset transcription state and re-queue the audio for processing."""
    rec = set_processing(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    background.add_task(process_recording, rec.id)
    return _recording_to_dict(rec)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/recordings/{rid}")
def delete_recording_endpoint(
    rid: int,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Delete the database row and the audio file from disk."""
    rec = delete_recording(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    path = Path(rec.stored_path)
    path.unlink(missing_ok=True)
    return {"deleted": rid}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def stats_endpoint(session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Aggregate counts and totals across all recordings."""
    return get_stats(session)
