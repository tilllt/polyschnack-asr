"""Adapter for ARK-ASR via the CrispASR HTTP server (OpenAI-compatible).

CrispASR is a unified ggml speech engine: one binary, many backends, GGUF
models. It ships a server mode (``crispasr --server``) exposing
POST /v1/audio/transcriptions (OpenAI protocol) — the ark-asr backend
runs as its own container and is reached over the compose network.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result

log = logging.getLogger(__name__)

# URL of the ark-asr (CrispASR server) container in the compose network
_URL = os.getenv("CRISPR_ARK_URL", "http://crispr-ark:5095")


class CrispAsrHttpClient(AsrClient):
    """Connects to the CrispASR OpenAI-compatible HTTP server (ark-asr backend)."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=True,  # server returns segments with word timestamps
        languages=["de", "en"],
        device=["gpu"],
        label="crispr-ark",
        native_punctuation=True,  # Server: --punc-model fullstop --truecase-model lstm
    )

    def __init__(self, url: Optional[str] = None,
                 transport: Optional[httpx.BaseTransport] = None,
                 capabilities: Optional[BackendCapabilities] = None) -> None:
        self.url = (url or _URL).rstrip("/")
        self._transport = transport
        # Per-Instanz-Override (moonshine-de/canary-asr nutzen denselben
        # Adapter mit eigener Capability-Beschreibung, Task C6).
        if capabilities is not None:
            self.capabilities = capabilities

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Transcribe via POST /v1/audio/transcriptions (verbose_json)."""
        try:
            with httpx.Client(timeout=3600, transport=self._transport) as client:
                resp = client.post(
                    f"{self.url}/v1/audio/transcriptions",
                    files={"file": (filename, audio_bytes, mime)},
                    data={
                        "response_format": "verbose_json",
                        "timestamp_granularities": "word",
                    },
                )
                resp.raise_for_status()
                return _parse_result(resp.json())
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Backend {self.capabilities.label} nicht erreichbar ({self.url}). "
                "Ist der Container gestartet? (Admin-Bereich → Backends)"
            ) from exc
