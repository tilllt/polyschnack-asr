"""Feature matrix for the ASR backends — README + GUI (Task 3).

Flattens the service registry into the public matrix shape. The registry is
the single source of truth; values marked ``"verify"`` (e.g. ark/voxtral
``word_timestamps``) are checked against real API responses before being
flipped to booleans.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from ..service_registry import SERVICES

router = APIRouter(prefix="/api/models")


def build_matrix() -> List[Dict[str, Any]]:
    """Return one entry per registry service in the public matrix shape."""
    out: List[Dict[str, Any]] = []
    for s in SERVICES:
        caps = s["capabilities"]
        out.append({
            "name": s["name"],
            "backend": s["backend"],
            "model": s["model"],
            "type": s["type"],
            "status": s["status"],
            "concurrency": s["concurrency"],
            "device": caps["device"],
            "languages": caps["languages"],
            "word_timestamps": caps["word_timestamps"],
            "streaming": caps["streaming"],
            "async_jobs": caps["async_jobs"],
            "noise_reduce": caps["noise_reduce"],
            "vad": caps["vad"],
            "diarization": caps["diarization"],
            "enhance": caps["enhance"],
            "requires": s["requires"],
        })
    return out


@router.get("/matrix")
def models_matrix() -> List[Dict[str, Any]]:
    return build_matrix()
