"""Adapter for ARK-ASR via CrispASR (ggml/C++ engine with ARK-ASR backend)."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess as sp
import tempfile
from typing import Any, Dict, List

from .. import AsrClient, BackendCapabilities

log = logging.getLogger(__name__)

_CLI_PATH = os.getenv("CRISPASR_CLI", "crispasr")
_ASR_MODEL = os.getenv("ARK_ASR_MODEL", "/models/ark-asr-3b-q8_0.gguf")
_ASR_BACKEND = "ark-asr"  # CrispASR backend name


class CrispAsrClient(AsrClient):
    """Transcribes audio via CrispASR CLI with ARK-ASR backend."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=False,  # unverified — registry carries "verify" until tested
        languages=["de", "en"],
        device=["gpu"],
        label="ark-asr",
    )

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Run crispasr --backend ark-asr → transcription text.

        CrispASR outputs plain text (no JSON timestamps) via the CLI.
        Word timestamps are estimated as uniform distribution.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            cmd = [
                _CLI_PATH,
                "-m", _ASR_MODEL,
                "--backend", _ASR_BACKEND,
                "-f", tmp_path,
            ]
            log.info("Running: %s", " ".join(cmd))

            result = sp.run(
                cmd,
                capture_output=True,
                timeout=3600,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")[:500]
                log.error("crispasr failed (exit=%d): %s",
                          result.returncode, stderr)
                raise RuntimeError(f"crispasr failed: {stderr}")

            stdout = result.stdout.decode(errors="replace").strip()
            return _parse_crispasr_output(stdout)

        except sp.TimeoutExpired:
            raise RuntimeError("crispasr timed out after 3600s")
        except FileNotFoundError:
            raise RuntimeError(
                f"crispasr not found at {_CLI_PATH}. "
                "Ensure it's in PATH or set CRISPASR_CLI env var."
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _parse_crispasr_output(stdout: str) -> Dict[str, Any]:
    """Parse CrispASR stdout → canonical {text, segments[], duration, language}.

    CrispASR outputs plain transcription text.  We build a single segment
    with uniform word-timestamp distribution.
    """
    text = stdout.strip()
    words = text.split()
    n_words = max(len(words), 1)

    # Estimate ~300ms per word for timing fallback
    dur = max(n_words * 0.3, 1.0)
    w_dur = dur / n_words

    word_list: List[Dict[str, Any]] = [
        {"word": w, "start": i * w_dur, "end": (i + 1) * w_dur}
        for i, w in enumerate(words)
    ]

    segments: List[Dict[str, Any]] = [{
        "start": 0.0,
        "end": dur,
        "text": text,
        "words": word_list,
    }]

    return {
        "text": text,
        "segments": segments,
        "duration": dur,
        "language": None,
    }
