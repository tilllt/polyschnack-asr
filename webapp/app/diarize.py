"""Minimal pyannote.audio diarization wrapper.

Requires HF_TOKEN env var (accept terms at
https://huggingface.co/pyannote/speaker-diarization-3.1 and
https://huggingface.co/pyannote/segmentation-3.0).

Silently returns empty list when token is missing (no crash).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger(__name__)

_pipeline = None


def _load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    token = os.getenv("HF_TOKEN")
    if not token:
        log.warning("HF_TOKEN not set — diarization disabled")
        return None
    from pyannote.audio import Pipeline
    _pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=token,
    )
    log.info("pyannote diarization pipeline loaded")
    return _pipeline


def diarize(audio_path: str) -> List[Dict[str, Any]]:
    """Run speaker diarization on *audio_path*.

    Returns a list of ``{"start": float, "end": float, "speaker": str}`` dicts,
    or an empty list when diarization is unavailable.
    """
    pipeline = _load_pipeline()
    if pipeline is None:
        log.warning("diarize(%s): pipeline not loaded (HF_TOKEN missing or pyannote not installed)", audio_path)
        return []

    log.info("diarize: running pyannote pipeline on %s", audio_path)
    try:
        result = pipeline(audio_path)
    except Exception as exc:
        log.exception("diarize: pipeline() threw on %s: %s", audio_path, exc)
        return []

    segments: List[Dict[str, Any]] = []
    for turn, _, speaker in result.itertracks(yield_label=True):
        segments.append({
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "speaker": speaker,
        })
    segments.sort(key=lambda s: s["start"])
    speaker_set = set(s["speaker"] for s in segments)
    log.info("diarize: %d segments, %d speakers (%s)",
             len(segments), len(speaker_set),
             ", ".join(sorted(speaker_set)) if speaker_set else "none")
    return segments
