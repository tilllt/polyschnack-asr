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
from .recordings import _convert_to_wav_if_needed, _current_user, _recording_to_dict

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/recordings/from-url", status_code=201)
async def import_from_url(
    request: Request,
    url: str = Form(...),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    diarize_num_speakers: Optional[int] = Form(None),
    diarize_min_duration_off: Optional[float] = Form(None),
    diarize_method: Optional[str] = Form(None),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
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
                    "-f", "ba/b",  # nur Audio-Stream laden (ba=best audio, b=Fallback)
                    "-x",
                    "--audio-format", "wav",
                    "--audio-quality", "0",
                    "-o", out_template,
                    "--no-playlist",
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

        # YouTube blockt Datacenter-IPs intermittierend (Bot-Schutz, flaky 403).
        # Ein Fehlschlag ist meist in <2 s fertig — ein zweiter Versuch hat
        # gute Erfolgschancen und macht den Import spürbar robuster.
        if proc.returncode != 0:
            retry_proc = subprocess.run(
                [
                    "yt-dlp",
                    "-f", "ba/b",
                    "-x",
                    "--audio-format", "wav",
                    "--audio-quality", "0",
                    "-o", out_template,
                    "--no-playlist",
                    url.strip(),
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if retry_proc.returncode == 0:
                proc = retry_proc

        if proc.returncode != 0:
            err = (proc.stderr or "no output")[:500]
            log.warning("yt-dlp failed for url=%s: %s", url[:80], err)
            hint = _ytdlp_error_hint(err, url)
            detail = f"yt-dlp failed: {err}"
            if hint:
                detail += f" — {hint}"
            raise HTTPException(status_code=400, detail=detail)

        # WICHTIG: NICHT auf --print filename verlassen — das druckt den
        # Namen VOR der Audio-Extraktion (z.B. .mp4 statt .wav). Stattdessen
        # suchen wir die erzeugte WAV-Datei im Tempdir.
        wavs = sorted(Path(tmpdir).glob("*.wav"))
        if not wavs:
            raise HTTPException(status_code=400, detail="yt-dlp produced no audio file")
        wav_path = wavs[0]

        audio_data = wav_path.read_bytes()

    if not audio_data:
        raise HTTPException(status_code=400, detail="empty audio downloaded")

    # yt-dlp liefert je nach Quelle 44.1/48 kHz (Stereo). ASR-Service,
    # Peak-Berechnung und WaveSurfer erwarten 16 kHz mono → wie beim
    # Upload-Pfad konvertieren.
    audio_data, _, conv_note = _convert_to_wav_if_needed(audio_data, "audio.wav")

    content_hash = hashlib.blake2b(audio_data, digest_size=16).hexdigest()
    current_user_id = _current_user(request, session)
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()
    # Dedup NUR innerhalb derselben Identität: eine fremde Recording
    # zurückzugeben würde im Frontend als „Import ok" wirken, aber die
    # Aufnahme gehört einem anderen anon-User → Transcribe schlägt dort
    # mit 403 „requires at least 'full' access" fehl (stiller Fehler).
    if existing and existing.user_id == current_user_id:
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
        diarize_num_speakers=diarize_num_speakers,
        diarize_min_duration_off=diarize_min_duration_off,
        diarize_method=diarize_method,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        content_hash=content_hash,
        user_id=current_user_id,  # session nötig (anon-Identität)
    )
    return _recording_to_dict(rec)


def _ytdlp_error_hint(stderr: str, url: str) -> str | None:
    """Verständlicher Zusatzhinweis für bekannte yt-dlp-Fehlerbilder.

    YouTube blockt Datacenter-IPs regelmäßig mit Bot-Schutz (403/„Sign in
    to confirm you're not a bot"). Der User soll wissen, dass das nicht an
    der App liegt — statt nur den rohen yt-dlp-Text zu sehen.
    """
    low = stderr.lower()
    is_youtube = "youtube" in url.lower() or "youtu.be" in url.lower()
    if is_youtube and (
        "sign in to confirm you're not a bot" in low
        or "http error 403" in low
        or "http error 400" in low
        or "video unavailable" in low
    ):
        return (
            "YouTube hat den Download abgelehnt (Bot-Schutz oder "
            "Alters-/Regionsbeschränkung). Bitte später erneut versuchen "
            "oder eine andere Quelle nutzen."
        )
    return None
