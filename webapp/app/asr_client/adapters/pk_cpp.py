"""Adapter for parakeet.cpp (CrispASR-Server, parakeet-Backend), OpenAI-kompatibel."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result

log = logging.getLogger(__name__)

# URL des eigenen pk-cpp-Containers (CrispASR-Server) im Compose-Netzwerk.
# Achtung: NICHT settings.ASR_URL — das ist der ONNX-pk-python-Container
# (http://asr:5092). Der cpp-Container hat seinen eigenen Dienst.
_CPP_URL = os.getenv("CPP_URL", "http://polyschnack-cpp:5093")


class PkCppClient(AsrClient):
    """Connects to the CrispASR parakeet server (OpenAI-compatible)."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=True,  # parakeet, via -ml 1 auf dem Server
        languages=["de", "en"],
        device=["gpu", "cpu"],
        label="pk-cpp",
        native_punctuation=True,  # Server: --punc-model fullstop --truecase-model lstm
    )

    def __init__(self, url: Optional[str] = None,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self.url = (url or _CPP_URL).rstrip("/")
        self._transport = transport

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Transcribe via POST /v1/audio/transcriptions (OpenAI-compatible).

        CrispASR supports response_format=verbose_json with word timestamps
        (nativ via -ml 1).  ``noise_reduce`` is ignored — the ggml backend
        has no such option.
        """
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
                f"Backend pk-cpp nicht erreichbar ({self.url}). "
                "Ist der Container gestartet? (Admin-Bereich → Backends)"
            ) from exc
