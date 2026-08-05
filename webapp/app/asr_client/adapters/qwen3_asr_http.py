"""Adapter for qwen3-asr.cpp server (HTTP, OpenAI-compatible).

The qwen3-asr backend runs as its own container (``qwen3-asr:5094``,
``qwen3-asr-server`` entrypoint). The webapp talks to it over the compose
network via POST /v1/audio/transcriptions — no local CLI binary needed.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result

log = logging.getLogger(__name__)

# URL of the qwen3-asr container in the compose network (override via env)
_URL = os.getenv("QWEN3_URL", "http://qwen3-asr:5094")


class Qwen3AsrHttpClient(AsrClient):
    """Connects to the qwen3-asr.cpp OpenAI-compatible HTTP server."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=True,  # via forced aligner model on the server
        languages=["de", "en"],
        device=["gpu"],
        label="qwen3-asr",
        native_punctuation=True,  # Server: --punc-model fullstop --truecase-model lstm
    )

    def __init__(self, url: Optional[str] = None,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self.url = (url or _URL).rstrip("/")
        self._transport = transport

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
                f"Backend qwen3-asr nicht erreichbar ({self.url}). "
                "Ist der Container gestartet? (Admin-Bereich → Backends)"
            ) from exc
