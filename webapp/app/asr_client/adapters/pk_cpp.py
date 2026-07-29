"""Adapter for parakeet.cpp (ggml/C++ backend), OpenAI-compatible server."""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result
from ..config import settings

log = logging.getLogger(__name__)


class PkCppClient(AsrClient):
    """Connects to a parakeet.cpp OpenAI-compatible server (mudler/parakeet.cpp)."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        label="pk-cpp",
    )

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Transcribe via POST /v1/audio/transcriptions (OpenAI-compatible).

        parakeet.cpp supports response_format=verbose_json with
        timestamp_granularities[]=word.  ``noise_reduce`` is ignored — the
        ggml backend has no such option.
        """
        with httpx.Client(timeout=3600) as client:
            resp = client.post(
                f"{settings.ASR_URL}/v1/audio/transcriptions",
                files={"file": (filename, audio_bytes, mime)},
                data={
                    "response_format": "verbose_json",
                    "timestamp_granularities": "word",
                },
            )
            resp.raise_for_status()
            return _parse_result(resp.json())
