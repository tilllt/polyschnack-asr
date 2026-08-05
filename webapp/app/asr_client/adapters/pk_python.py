"""Adapter for the existing Python/ONNX ASR backend (pk-asr)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result
from ...config import settings

log = logging.getLogger(__name__)


class PkPythonClient(AsrClient):
    """Connects to the Python/ONNX parakeet backend (the current PolySchnack pk-python backend)."""

    capabilities = BackendCapabilities(
        streaming=True,
        async_jobs=True,
        noise_reduce=True,
        word_timestamps=True,  # parakeet TDT emits word timestamps model-inherently
        languages=["de", "en"],
        device=["gpu", "cpu"],
        label="ps-pk-onnx",
    )

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        """OpenAI-compatible ASR client.

        ``url`` defaults to ``settings.ASR_URL``; ``api_key`` adds an
        Authorization header (used for the Voxtral/vLLM endpoint, Task 6).
        """
        self.url = (url or settings.ASR_URL).rstrip("/")
        self.api_key = api_key

    def _headers(self) -> Optional[Dict[str, str]]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Send audio via sync (batched) endpoint."""
        with httpx.Client(timeout=3600) as client:
            resp = client.post(
                f"{self.url}/v1/audio/transcriptions",
                headers=self._headers(),
                files={"file": (filename, audio_bytes, mime)},
                data={
                    "model": settings.ASR_MODEL,
                    "response_format": "verbose_json",
                    "timestamp_granularities": "word",
                    "noise_reduce": "true" if noise_reduce else "false",
                },
            )
            resp.raise_for_status()
            return _parse_result(resp.json())

    def transcribe_streaming(
        self,
        audio_bytes: bytes,
        filename: str,
        mime: str,
        noise_reduce: bool = True,
        on_chunk: Optional[Callable[[str, int, int, float, float, bool], None]] = None,
    ) -> Dict[str, Any]:
        """SSE streaming via /v1/audio/transcriptions/stream."""
        accumulated: List[str] = []
        segments: List[Dict[str, Any]] = []
        final_text = ""
        total_chunks = 1
        data = {
            "model": settings.ASR_MODEL,
            "noise_reduce": "true" if noise_reduce else "false",
        }

        with httpx.Client(timeout=3600) as client:
            with client.stream(
                "POST",
                f"{self.url}/v1/audio/transcriptions/stream",
                headers=self._headers(),
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
            "duration": None,
            "language": None,
        }

    def transcribe_async(
        self,
        audio_bytes: bytes,
        filename: str,
        mime: str,
        noise_reduce: bool = True,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Async job via /v1/audio/transcriptions/async + polling."""
        with httpx.Client(timeout=10) as client:
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

            max_polls = 1800
            for _ in range(max_polls):
                time.sleep(1)
                try:
                    status_resp = client.get(
                        f"{settings.ASR_URL}/v1/audio/jobs/{job_id}", timeout=5
                    )
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
