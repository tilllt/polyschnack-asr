"""POST /api/recordings/from-url — download audio from a URL via yt-dlp."""
from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlmodel import Session, select

from ..config import settings
from ..crud import create_recording
from ..db import get_session
from ..models import Recording
from .recordings import _current_user, _recording_to_dict

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/recordings/from-url", status_code=201)
async def import_from_url(
    request: Request,
    url: str = Form(...),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Download audio from *url* via yt-dlp, convert to 16 kHz mono WAV, save."""
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="no URL provided")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "audio.%(ext)s"
        out_template = str(tmp)

        try:
            proc = subprocess.run(
                [
                    "yt-dlp",
                    "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "-x",
                    "--audio-format", "wav",
                    "--audio-quality", "0",
                    "-o", out_template,
                    "--no-playlist",
                    "--print", "filename",
                    url.strip(),
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=400, detail="URL download timed out (10 min)")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="yt-dlp not installed")

        if proc.returncode != 0:
            err = (proc.stderr or "no output")[:500]
            raise HTTPException(status_code=400, detail=f"yt-dlp failed: {err}")

        wav_path_str = proc.stdout.strip().split("\n")[0].strip()
        wav_path = Path(wav_path_str)
        if not wav_path.exists():
            found = list(Path(tmpdir).glob("*.wav"))
            if not found:
                raise HTTPException(status_code=400, detail="yt-dlp produced no audio file")
            wav_path = found[0]

        audio_data = wav_path.read_bytes()

    if not audio_data:
        raise HTTPException(status_code=400, detail="empty audio downloaded")

    content_hash = hashlib.blake2b(audio_data, digest_size=16).hexdigest()
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()
    if existing:
        return _recording_to_dict(existing)

    stored = settings.AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
    stored.write_bytes(audio_data)

    est_duration_s = len(audio_data) / 16000

    rec = create_recording(
        session,
        original_name=f"URL: {url[:80]}",
        stored_path=str(stored),
        mime="audio/wav",
        size_bytes=len(audio_data),
        duration_s=est_duration_s,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        content_hash=content_hash,
        user_id=_current_user(request),
    )
    return _recording_to_dict(rec)
