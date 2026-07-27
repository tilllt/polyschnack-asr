"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import subprocess as sp
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from sqlmodel import Session

from . import asr_client, crud
from .asr_client import transcribe as _sync_transcribe
from .asr_client import transcribe_async, transcribe_streaming
from .crud import get_or_create_user, get_user, set_progress
from .db import engine
from .diarize import diarize as run_diarization
from .peaks import compute_peaks
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
        enable_vad = rec.enable_vad
        enable_diarize = rec.enable_diarize
        enable_streaming = rec.enable_streaming
        enable_noise_reduce = rec.enable_noise_reduce

    log.info("process_recording rec_id=%s: vad=%s diarize=%s streaming=%s noise=%s",
             rec_id, enable_vad, enable_diarize, enable_streaming, enable_noise_reduce)

    t0 = time.perf_counter()
    status = "done"
    text: str = ""
    duration = None
    language = None
    segments: List[Dict[str, Any]] = []
    error = None
    peaks = None

    try:
        audio_bytes = audio_path.read_bytes()

        # Mark progress: 10% — loaded
        with Session(engine) as session:
            set_progress(session, rec_id, 10)

        # Optional VAD silence trimming
        if _VAD_TRIM and enable_vad:
            trimmed = _trim_silence(audio_bytes)
            if len(trimmed) < len(audio_bytes):
                log.info("VAD trim: rec_id=%s %d→%d bytes (%.1fs saved)", rec_id, len(audio_bytes), len(trimmed), (len(audio_bytes) - len(trimmed)) / (2 * 16000))
            audio_bytes = trimmed

        with Session(engine) as session:
            set_progress(session, rec_id, 20)

        # Run ASR (batched sync or SSE streaming)
        if enable_streaming:

            def _on_chunk(acc_text: str, idx: int, total: int, start: float, end: float, final: bool):
                pct = int((idx + 1) / total * 70) + 10
                with Session(engine) as session:
                    set_progress(session, rec_id, pct)
                    if acc_text:
                        rec = crud.get_recording(session, rec_id)
                        if rec:
                            rec.text = acc_text
                            session.add(rec)
                            session.commit()

            result = transcribe_streaming(
                audio_bytes, filename, mime,
                noise_reduce=enable_noise_reduce,
                on_chunk=_on_chunk,
            )
            with Session(engine) as session:
                set_progress(session, rec_id, 80)
        else:
            def _on_progress(pct: int):
                with Session(engine) as s:
                    set_progress(s, rec_id, pct)
            result = transcribe_async(
                audio_bytes, filename, mime,
                noise_reduce=enable_noise_reduce,
                on_progress=_on_progress,
            )
            with Session(engine) as session:
                set_progress(session, rec_id, 95)

        text = result["text"]
        duration = result["duration"]
        language = result["language"]
        segments = result["segments"]

        # Optional speaker diarization — merge labels into segments
        if enable_diarize:
            log.info("Diarization ENABLED for rec_id=%s — calling run_diarization(%s)", rec_id, audio_path)
            try:
                diar = run_diarization(str(audio_path))
                log.info("Diarization returned %d segments for rec_id=%s", len(diar or []), rec_id)
            except Exception as exc_d:
                log.exception("Diarization threw for rec_id=%s: %s", rec_id, exc_d)
                diar = None
        else:
            diar = None
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
            labeled = sum(1 for s in segments if s.get("speaker"))
            log.info("Speaker merge: %d/%d segments labeled for rec_id=%s", labeled, len(segments), rec_id)
        # Compute waveform peaks for fast WaveSurfer render
        try:
            audio_bytes_for_peaks = audio_path.read_bytes()
            peaks = compute_peaks(audio_bytes_for_peaks)
        except Exception:
            log.exception("peaks: compute failed for rec_id=%s", rec_id)
            peaks = None
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
            waveform_peaks=peaks,
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


# ---------------------------------------------------------------------------
# Audio trimming (for crop — uses ffmpeg)
# ---------------------------------------------------------------------------


def trim_audio(audio_bytes: bytes, start: float, end: float) -> bytes:
    """FFmpeg-based audio trim — returns 16kHz mono WAV bytes."""
    with tempfile.NamedTemporaryFile(suffix=".in") as fin, \
         tempfile.NamedTemporaryFile(suffix=".wav") as fout:
        fin.write(audio_bytes)
        fin.flush()
        dur = end - start
        sp.run([
            "ffmpeg", "-y", "-i", fin.name,
            "-ss", str(start), "-t", str(dur),
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            fout.name,
        ], capture_output=True, check=True)
        return fout.read()
