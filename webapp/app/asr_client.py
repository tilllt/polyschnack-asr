"""HTTP client for the ASR inference service.

``transcribe()`` is a synchronous function meant to be called from a
background thread (e.g. via ``asyncio.get_event_loop().run_in_executor`` or
FastAPI ``BackgroundTasks``).  It never touches the database.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from .config import settings


def transcribe(
    audio_bytes: bytes,
    filename: str,
    mime: str,
) -> Dict[str, Any]:
    """Send *audio_bytes* to the ASR service and return parsed results.

    The ASR endpoint is called with ``response_format=verbose_json`` so
    that segment-level timestamps are always included.

    Returns a dict with keys:
      - ``text`` (str): full transcript
      - ``duration`` (float | None): audio duration in seconds
      - ``language`` (str | None): detected language code
      - ``segments`` (list[dict]): list of ``{start, end, text}`` dicts

    Raises ``httpx.HTTPStatusError`` on non-2xx responses and
    ``httpx.RequestError`` on network failures — callers must handle both.
    """
    with httpx.Client(timeout=3600) as client:
        response = client.post(
            f"{settings.ASR_URL}/v1/audio/transcriptions",
            files={"file": (filename, audio_bytes, mime)},
            data={"model": settings.ASR_MODEL, "response_format": "verbose_json"},
        )
        response.raise_for_status()
        payload = response.json()

    segments: List[Dict[str, Any]] = [
        {
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg.get("text", ""),
        }
        for seg in payload.get("segments", [])
    ]

    return {
        "text": payload.get("text", ""),
        "duration": payload.get("duration"),
        "language": payload.get("language"),
        "segments": segments,
    }
