"""HTTP client for the ASR inference service.

``transcribe()`` — synchronous, uses batched endpoint.
``transcribe_streaming()`` — synchronous SSE-based, calls *on_chunk(...)* per event.

Backend selection via ``ASR_BACKEND`` env var (default: ``ps-pk-onnx``).
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
    label: str = "ps-pk-onnx"
    #: Backend liefert Interpunktion nativ (CrispASR-Server mit
    #: --punc-model) — die Webapp darf dann KEINE LLM-Punctuation
    #: nachschalten (sonst doppelte/konkurrierende Interpunktion).
    native_punctuation: bool = False


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

# Alias-Kompatibilität: alte/alternative Backend-Namen → kanonische ID.
_BACKEND_ALIASES = {
    "crispasr": "crispr-ark",
    "crisp-asr": "crispr-ark",
}


def _resolve_backend(backend: str) -> Dict[str, Any]:
    """Registry-Eintrag für eine Backend-ID (inkl. Alias-Auflösung)."""
    from ..service_registry import get_service

    canonical = _BACKEND_ALIASES.get(backend, backend)
    svc = get_service(canonical) or {}
    if not svc:
        raise ValueError(f"unknown backend: {backend}")
    return svc


def _load_adapter(svc: Dict[str, Any]) -> AsrClient:
    """Instanziiert den Adapter aus dem ``adapter``-Feld (Modul:Klassenname).

    URL-Auflösung (Option C):
    1. Env-Override ``<ID>_URL`` (z. B. ``CRISPR_QWEN3_URL``) — abgeleitet
       aus der Backend-ID, kein manuelles url_env-Feld.
    2. Sonst Compose-Netzwerk-URL aus ``name`` + ``port``
       (z. B. http://crispr-qwen3:5094) — deterministisch, keine URL im YAML.
    """
    import importlib
    import inspect

    from ..service_registry import service_url, service_url_env

    module_name, _, class_name = svc["adapter"].partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)

    kwargs: Dict[str, Any] = {}
    url = os.getenv(service_url_env(svc))
    url = url or service_url(svc)
    if url:
        kwargs["url"] = url

    # Optionale Konstruktor-Argumente aus der YAML (adapter_kwargs).
    # Schlüssel mit *_env-Suffix: der Wert ist der Env-Var-Name.
    for key, value in (svc.get("adapter_kwargs") or {}).items():
        if key.endswith("_env"):
            kwargs[key[:-4]] = os.getenv(value, "")
        else:
            kwargs[key] = value

    # Per-Adapter-Capabilities (moonshine-de/canary-asr teilen den
    # CrispAsrHttpClient — gleicher Adapter, eigene Feature-Beschreibung).
    if "capabilities" in inspect.signature(cls.__init__).parameters:
        caps = svc.get("capabilities", {})
        wt = caps.get("word_timestamps", False)
        kwargs["capabilities"] = BackendCapabilities(
            streaming=bool(caps.get("streaming", False)),
            async_jobs=bool(caps.get("async_jobs", False)),
            noise_reduce=bool(caps.get("noise_reduce", False)),
            word_timestamps=wt is True,  # "verify" (unbestätigt) → False
            languages=list(caps.get("languages", [])),
            device=list(caps.get("device", [])),
            label=svc["name"],
            native_punctuation=bool(caps.get("native_punctuation", True)),
        )
    client = cls(**kwargs)
    # capabilities_override (YAML): nachträglich setzen, wenn die Klasse
    # keinen Konstruktor-Parameter hat (z. B. PkPythonClient für voxtral).
    if svc.get("capabilities_override") and "capabilities" not in kwargs:
        caps = svc["capabilities_override"]
        wt = caps.get("word_timestamps", False)
        client.capabilities = BackendCapabilities(
            streaming=bool(caps.get("streaming", False)),
            async_jobs=bool(caps.get("async_jobs", False)),
            noise_reduce=bool(caps.get("noise_reduce", False)),
            word_timestamps=wt is True,
            languages=list(caps.get("languages", [])),
            device=list(caps.get("device", [])),
            label=svc["name"],
            native_punctuation=bool(caps.get("native_punctuation", False)),
        )
    return client


def get_client(backend: Optional[str] = None) -> AsrClient:
    """Return the adapter for *backend*.

    With ``backend=None`` the singleton selected by ``ASR_BACKEND`` env var is
    returned (legacy behaviour). An explicit backend builds a fresh client —
    this is the queue path (each job is bound to its endpoint, Task 6).
    """
    global _client_instance
    explicit = backend is not None
    backend = backend or os.getenv("ASR_BACKEND", "ps-pk-onnx") or "ps-pk-onnx"

    if not explicit and _client_instance is not None:
        return _client_instance

    try:
        svc = _resolve_backend(backend)
        client = _load_adapter(svc)
    except ValueError:
        # Unbekannter Backend-Name → Fallback auf das Default-Backend
        # (ps-pk-onnx), damit alte config.json-Werte nicht crashen.
        log.warning("Unbekannter ASR-Backend %r — Fallback auf ps-pk-onnx", backend)
        svc = _resolve_backend("ps-pk-onnx")
        client = _load_adapter(svc)
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

    CrispASR liefert pro Token ``probability`` (token.p, 0.0-1.0) — das
    wird als ``confidence`` an das fertige Wort durchgereicht (Task 3,
    Per-Token-Confidence-Färbung in der GUI). Bei ##-Continuationen
    gewinnt die Confidence des letzten Tokens (das vollständige Wort).
    """
    merged: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None
    for t in tokens:
        w = t.get("word", "")
        s = t.get("start")
        e = t.get("end")
        p = t.get("probability")
        if w.startswith("##") and cur is not None:
            cur["word"] += w[2:]
            if e is not None:
                cur["end"] = e
            if p is not None:
                cur["confidence"] = p
        else:
            if cur is not None:
                merged.append(cur)
            cur = {"word": w, "start": s, "end": e}
            if p is not None:
                cur["confidence"] = p
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
        # CrispASR: Segment-Level-Log-Probabilität (Durchschnitt über die
        # Token) — optional, fürs UI-Diagnose-Tooling (Task 3).
        if "avg_logprob" in seg:
            segments[-1]["avg_logprob"] = seg["avg_logprob"]
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
