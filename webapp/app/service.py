"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from sqlmodel import Session

from . import asr_client, crud
from .db import engine
from .diarize import diarize as run_diarization
from .vad import trim_silence as _trim_silence
import os

_VAD_TRIM = os.getenv("VAD_TRIM_SILENCE", "false").lower() in ("true", "1", "yes")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------


def process_recording(rec_id: int) -> None:
    """Load row → read audio → call ASR → persist result.

    Designed to run in a background thread (FastAPI BackgroundTasks).
    All exceptions are caught so a transient failure cannot crash the worker;
    the row is updated to status='failed' with the error message.
    """
    with Session(engine) as session:
        rec = crud.get_recording(session, rec_id)
        if rec is None:
            log.warning("process_recording: rec_id=%d not found, skipping", rec_id)
            return
        audio_path = Path(rec.stored_path)
        filename = rec.original_name
        mime = rec.mime or "application/octet-stream"

    t0 = time.perf_counter()
    status = "done"
    text: str = ""
    duration = None
    language = None
    segments: List[Dict[str, Any]] = []
    error = None

    try:
        audio_bytes = audio_path.read_bytes()

        # Optional VAD silence trimming
        if _VAD_TRIM:
            trimmed = _trim_silence(audio_bytes)
            if len(trimmed) < len(audio_bytes):
                log.info("VAD trim: rec_id=%d %d→%d bytes (%.1fs saved)", rec_id, len(audio_bytes), len(trimmed), (len(audio_bytes) - len(trimmed)) / (2 * 16000))
            audio_bytes = trimmed

        result = asr_client.transcribe(audio_bytes, filename, mime)
        text = result["text"]
        duration = result["duration"]
        language = result["language"]
        segments = result["segments"]

        # Optional speaker diarization — merge labels into segments
        diar = run_diarization(str(audio_path))
        if diar:
            sd_idx = 0
            for seg in segments:
                s_start = seg.get("start", 0)
                s_end = seg.get("end", 0)
                speakers = set()
                while sd_idx < len(diar) and diar[sd_idx]["end"] <= s_start:
                    sd_idx += 1
                for d in diar[sd_idx:]:
                    if d["start"] >= s_end:
                        break
                    if d["start"] < s_end and d["end"] > s_start:
                        speakers.add(d["speaker"])
                if speakers:
                    seg["speaker"] = "/".join(sorted(speakers))
    except Exception as exc:  # broad catch: any I/O or HTTP failure marks the row failed
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        log.exception("process_recording rec_id=%d failed", rec_id)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    with Session(engine) as session:
        crud.update_result(
            session,
            rec_id,
            status=status,
            text=text,
            duration_s=duration,
            language=language,
            segments=segments if segments else None,
            processing_ms=elapsed_ms,
            error=error,
        )


# ---------------------------------------------------------------------------
# Subtitle / export helpers
# ---------------------------------------------------------------------------


def _format_timestamp_srt(seconds: float) -> str:
    """Format *seconds* as an SRT timestamp ``HH:MM:SS,mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format *seconds* as a WebVTT timestamp ``HH:MM:SS.mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into an SRT subtitle string."""
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp_srt(float(seg.get("start", 0)))
        end = _format_timestamp_srt(float(seg.get("end", 0)))
        speaker = seg.get("speaker", "")
        prefix = f"[{speaker}] " if speaker else ""
        text = prefix + seg.get("text", "").strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_vtt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into a WebVTT subtitle string."""
    lines: List[str] = ["WEBVTT\n"]
    for seg in segments:
        start = _format_timestamp_vtt(float(seg.get("start", 0)))
        end = _format_timestamp_vtt(float(seg.get("end", 0)))
        speaker = seg.get("speaker", "")
        prefix = f"[{speaker}] " if speaker else ""
        text = prefix + seg.get("text", "").strip()
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_txt(text: str) -> str:
    """Return the plain transcript, normalising line endings."""
    return text.strip() + "\n"
