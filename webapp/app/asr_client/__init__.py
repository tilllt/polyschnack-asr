"""HTTP client for the ASR inference service.

``transcribe()`` — synchronous, uses batched endpoint.
``transcribe_streaming()`` — synchronous SSE-based, calls *on_chunk(...)* per event.

Backend selection via ``ASR_BACKEND`` env var (default: ``pk-python``).
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx

from ..config import settings

log = logging.getLogger(__name__)

# ============================================================
# Backend capabilities
# ============================================================


@dataclass
class BackendCapabilities:
    """Describes what a backend supports — frontend reads this via /api/models/status."""
    streaming: bool = False
    async_jobs: bool = False
    noise_reduce: bool = False
    word_timestamps: bool = False
    languages: List[str] = field(default_factory=list)
    device: List[str] = field(default_factory=lambda: ["cpu"])
    label: str = "pk-python"


# ============================================================
# Abstract client
# ============================================================


class AsrClient(ABC):
    """Interface every ASR backend adapter implements."""

    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)

    @abstractmethod
    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Transcribe audio → {text, segments[], duration, language}."""
        ...

    def transcribe_streaming(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
        on_chunk: Optional[Callable[[str, int, int, float, float, bool], None]] = None,
    ) -> Dict[str, Any]:
        """Optional SSE streaming — raises NotImplementedError by default."""
        raise NotImplementedError("streaming not supported by this backend")

    def transcribe_async(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Optional async job — falls back to sync transcribe by default."""
        log.info("transcribe_async: backend has no async support, using sync fallback")
        return self.transcribe(audio_bytes, filename, mime, noise_reduce=noise_reduce)


# ============================================================
# Factory
# ============================================================

_client_instance: Optional[AsrClient] = None


def get_client(backend: Optional[str] = None) -> AsrClient:
    """Return the adapter for *backend*.

    With ``backend=None`` the singleton selected by ``ASR_BACKEND`` env var is
    returned (legacy behaviour). An explicit backend builds a fresh client —
    this is the queue path (each job is bound to its endpoint, Task 6).
    """
    global _client_instance
    explicit = backend is not None
    backend = backend or os.getenv("ASR_BACKEND", "pk-python") or "pk-python"

    if not explicit and _client_instance is not None:
        return _client_instance

    if backend == "pk-cpp":
        from .adapters.pk_cpp import PkCppClient
        client = PkCppClient()
    elif backend == "qwen3-asr":
        from .adapters.qwen3_asr_http import Qwen3AsrHttpClient
        client = Qwen3AsrHttpClient()
    elif backend in ("ark-asr", "crispasr", "crisp-asr"):
        from .adapters.crisp_asr_http import CrispAsrHttpClient
        client = CrispAsrHttpClient()
    elif backend == "voxtral":
        # Voxtral runs on the local voxtral.cpp server (OpenAI-compatible API).
        from ..service_registry import get_service
        svc = get_service("voxtral") or {}
        from .adapters.pk_python import PkPythonClient
        client = PkPythonClient(
            url=svc.get("url"),
            api_key=os.getenv("POLYSCHNACK_VOXTRAL_API_KEY", ""),
        )
        client.capabilities = BackendCapabilities(
            streaming=True, async_jobs=False, noise_reduce=False,
            word_timestamps=False, languages=["de", "en"], device=["gpu"],
            label="voxtral",
        )
    else:
        from .adapters.pk_python import PkPythonClient
        client = PkPythonClient()
    log.info("ASR backend: %s", backend)

    if not explicit or _client_instance is None:
        _client_instance = client
    return client


# ============================================================
# Response parser (shared by all backends)
# ============================================================


def _merge_token_words(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge BPE-subword tokens into real words with real timestamps.

    Tokens starting with ``##`` are continuations of the previous word.
    A simple ``split()`` is the fallback when no tokens are available.
    """
    merged: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None
    for t in tokens:
        w = t.get("word", "")
        s = t.get("start")
        e = t.get("end")
        if w.startswith("##") and cur is not None:
            cur["word"] += w[2:]
            if e is not None:
                cur["end"] = e
        else:
            if cur is not None:
                merged.append(cur)
            cur = {"word": w, "start": s, "end": e}
    if cur is not None:
        merged.append(cur)
    return merged


def _parse_result(payload: dict) -> Dict[str, Any]:
    """Parse an OpenAI-format verbose_json response → canonical result dict.

    Keys returned: ``text``, ``segments[{start,end,text,words,?speaker}]``,
    ``duration``, ``language``.
    """
    segments: List[Dict[str, Any]] = []
    for seg in payload.get("segments", []):
        token_words = seg.get("words", [])
        if token_words:
            words = _merge_token_words(token_words)
        else:
            # Fallback: uniform distribution from text
            text_words = (seg.get("text") or seg.get("segment", "")).split()
            s = seg.get("start") or 0
            e = seg.get("end") or 0
            dur = max(e - s, 0.1)
            w_dur = dur / max(len(text_words), 1)
            words = [
                {"word": w, "start": s + i * w_dur, "end": s + (i + 1) * w_dur}
                for i, w in enumerate(text_words)
            ]
        segments.append({
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg.get("text") or seg.get("segment", ""),
            "words": words,
        })
    return {
        "text": payload.get("text", ""),
        "duration": payload.get("duration"),
        "language": payload.get("language"),
        "segments": segments,
    }


# ============================================================
# Legacy top-level functions (backward compat — kept for tests)
# ============================================================


def transcribe(audio_bytes: bytes, filename: str, mime: str,
               noise_reduce: bool = True) -> Dict[str, Any]:
    """Legacy entry point — delegates to get_client()."""
    return get_client().transcribe(audio_bytes, filename, mime,
                                   noise_reduce=noise_reduce)


def transcribe_streaming(
    audio_bytes: bytes, filename: str, mime: str,
    noise_reduce: bool = True,
    on_chunk: Optional[Callable[[str, int, int, float, float, bool], None]] = None,
) -> Dict[str, Any]:
    """Legacy entry point — delegates to get_client()."""
    return get_client().transcribe_streaming(
        audio_bytes, filename, mime,
        noise_reduce=noise_reduce, on_chunk=on_chunk,
    )


def transcribe_async(
    audio_bytes: bytes, filename: str, mime: str,
    noise_reduce: bool = True,
    on_progress: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Legacy entry point — delegates to get_client()."""
    return get_client().transcribe_async(
        audio_bytes, filename, mime,
        noise_reduce=noise_reduce, on_progress=on_progress,
    )
