"""HTTP client for the ASR inference service.

``transcribe()`` — synchronous, uses batched endpoint.
``transcribe_streaming()`` — synchronous SSE-based, calls *on_chunk(...)* per event.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)


def transcribe(audio_bytes: bytes, filename: str, mime: str, noise_reduce: bool = True) -> Dict[str, Any]:
    """Send audio via sync (batched) endpoint — faster, no live text."""
    with httpx.Client(timeout=3600) as client:
        resp = client.post(
            f"{settings.ASR_URL}/v1/audio/transcriptions",
            files=({"file": (filename, audio_bytes, mime)}),
            data={
                "model": settings.ASR_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities": "word",
                "noise_reduce": "true" if noise_reduce else "false",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    return _parse_result(payload)


def transcribe_streaming(
    audio_bytes: bytes,
    filename: str,
    mime: str,
    noise_reduce: bool = True,
    on_chunk: Optional[Callable[[str, int, int, float, float, bool], None]] = None,
) -> Dict[str, Any]:
    """Send audio via SSE streaming endpoint — slower but yields live text.

    *on_chunk(accumulated_text, chunk_index, total_chunks, start, end, is_final)*
    is called after each chunk finishes.
    """
    accumulated: List[str] = []
    segments: List[Dict[str, Any]] = []
    final_text = ""
    total_chunks = 1

    data = {"model": settings.ASR_MODEL, "noise_reduce": "true" if noise_reduce else "false"}

    with httpx.Client(timeout=3600) as client:
        with client.stream(
            "POST",
            f"{settings.ASR_URL}/v1/audio/transcriptions/stream",
            files={"file": (filename, audio_bytes, mime)},
            data=data,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if ev.get("error"):
                    raise RuntimeError(ev["error"])
                text = ev.get("text", "")
                if text:
                    accumulated.append(text)
                seg = {
                    "start": ev.get("start", 0),
                    "end": ev.get("end", 0),
                    "text": text,
                }
                segments.append(seg)
                total_chunks = ev.get("total_chunks", 1)
                if ev.get("final"):
                    final_text = ev.get("text", "")
                if on_chunk:
                    on_chunk(
                        " ".join(filter(None, accumulated)).strip(),
                        ev.get("chunk_index", 0),
                        total_chunks,
                        ev.get("start", 0),
                        ev.get("end", 0),
                        ev.get("final", False),
                    )

    return {
        "text": final_text or " ".join(filter(None, accumulated)).strip(),
        "segments": segments,
        "duration": None,  # filled in by service.py
        "language": None,
    }


def _parse_result(payload: dict) -> Dict[str, Any]:
    segments: List[Dict[str, Any]] = []
    for seg in payload.get("segments", []):
        words = seg.get("words", [])
        text = seg.get("text") or seg.get("segment", "")
        # If ASR didn't return word timestamps, generate proportional ones
        if not words and text.strip():
            s = seg.get("start", 0)
            e = seg.get("end", s + 0.1)
            text_words = text.strip().split()
            n = len(text_words)
            dur = max(e - s, 0.1)
            words = [
                {"word": w, "start": s + (i / n) * dur, "end": s + ((i + 1) / n) * dur}
                for i, w in enumerate(text_words)
            ]
        segments.append({"start": seg.get("start"), "end": seg.get("end"), "text": text, "words": words})
    return {
        "text": payload.get("text", ""),
        "duration": payload.get("duration"),
        "language": payload.get("language"),
        "segments": segments,
    }


def transcribe_async(
    audio_bytes: bytes,
    filename: str,
    mime: str,
    noise_reduce: bool = True,
    on_progress: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Submit audio via async job endpoint and poll until done.

    Returns the final result dict. Calls *on_progress(pct)* periodically.
    """
    with httpx.Client(timeout=10) as client:
        # Submit
        resp = client.post(
            f"{settings.ASR_URL}/v1/audio/transcriptions/async",
            files={"file": (filename, audio_bytes, mime)},
            data={
                "model": settings.ASR_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities": "word",
                "noise_reduce": "true" if noise_reduce else "false",
            },
        )
        resp.raise_for_status()
        job = resp.json()
        job_id = job["job_id"]

        # Poll until done (max 30 min)
        max_polls = 1800  # 1800 * 1s = 30 min
        for _ in range(max_polls):
            time.sleep(1)
            try:
                status_resp = client.get(f"{settings.ASR_URL}/v1/audio/jobs/{job_id}", timeout=5)
                status_resp.raise_for_status()
                data = status_resp.json()
            except Exception:
                continue

            pct = data.get("progress_pct", 0)
            if on_progress:
                on_progress(pct)

            if data["status"] == "done":
                return _parse_result(data)
            if data["status"] == "failed":
                raise RuntimeError(data.get("error", "async job failed"))
        raise TimeoutError("async job did not complete within 30 minutes")
