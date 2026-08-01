"""Adapter for qwen3-asr.cpp (GGML/C++ backend) with forced alignment.

Runs ``qwen3-asr-cli --transcribe-align`` as a subprocess — this gives
word-level timestamps via the forced aligner model.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess as sp
import tempfile
from typing import Any, Dict, List

from .. import AsrClient, BackendCapabilities

log = logging.getLogger(__name__)

# Paths to CLI binary and GGUF models (configurable via env)
_CLI_PATH = os.getenv("QWEN3_CLI", "qwen3-asr-cli")
_ASR_MODEL = os.getenv("QWEN3_ASR_MODEL", "/models/qwen3-asr-0.6b-q8_0.gguf")
_ALIGNER_MODEL = os.getenv("QWEN3_ALIGNER_MODEL", "/models/qwen3-forced-aligner-0.6b-f16.gguf")
_MAX_TOKENS = os.getenv("QWEN3_MAX_TOKENS", "1024")


class Qwen3AsrCppClient(AsrClient):
    """Transcribes audio with word-level timestamps via qwen3-asr-cli subprocess."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=True,  # via the forced aligner model
        languages=["de", "en"],
        device=["gpu"],
        label="qwen3-asr",
    )

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Run qwen3-asr-cli --transcribe-align → word timestamps.

        Steps:
        1. Save audio to a temp WAV file
        2. Invoke CLI with both ASR + forced aligner models
        3. Parse the JSON word-timestamp output
        4. Convert to canonical segments[] format
        """
        # Save audio bytes to temp WAV file (CLI expects 16kHz mono PCM)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            cmd = [
                _CLI_PATH,
                "-m", _ASR_MODEL,
                "--aligner-model", _ALIGNER_MODEL,
                "-f", tmp_path,
                "--transcribe-align",
                "--max-tokens", _MAX_TOKENS,
            ]
            log.info("Running: %s", " ".join(cmd))

            result = sp.run(
                cmd,
                capture_output=True,
                timeout=3600,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")[:500]
                log.error("qwen3-asr-cli failed (exit=%d): %s",
                          result.returncode, stderr)
                raise RuntimeError(f"qwen3-asr-cli failed: {stderr}")

            # Parse CLI output — the alignment JSON is in stdout
            stdout = result.stdout.decode(errors="replace")
            return _parse_cli_output(stdout)

        except sp.TimeoutExpired:
            raise RuntimeError("qwen3-asr-cli timed out after 3600s")
        except FileNotFoundError:
            raise RuntimeError(
                f"qwen3-asr-cli not found at {_CLI_PATH}. "
                "Ensure it's in PATH or set QWEN3_CLI env var."
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _parse_cli_output(stdout: str) -> Dict[str, Any]:
    """Parse qwen3-asr-cli stdout → {text, segments[], duration, language}.

    The CLI outputs JSON with word timestamps:
        {"words": [{"word": "...", "start": ..., "end": ...}, ...]}
    plus the raw transcription text before/after the JSON block.
    """
    # The CLI prints timing info and the "language <NAME>" prefix to stderr,
    # and the alignment JSON to stdout.  Extract JSON from stdout.
    words: List[Dict[str, Any]] = []
    full_text = ""

    # Try to find JSON block in stdout
    try:
        # Find the first { and last } to extract JSON
        start = stdout.index("{")
        end = stdout.rindex("}")
        payload = json.loads(stdout[start:end + 1])
        words = payload.get("words", [])

        # Also extract the raw transcription (printed before the JSON)
        # Format: "language <NAME> <transcription text>\n{...}"
        raw_lines = stdout[:start].strip()
        # Remove language prefix like "language German " or "language English "
        import re
        match = re.match(r"language\s+\S+\s+(.*)", raw_lines)
        if match:
            full_text = match.group(1).strip()
        else:
            full_text = raw_lines
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("Failed to parse alignment JSON: %s. Falling back to raw text.", exc)
        full_text = stdout.strip()

    # Build segments from words
    segments: List[Dict[str, Any]] = []
    if words:
        seg_text = " ".join(w["word"] for w in words)
        seg = {
            "start": words[0]["start"] if "start" in words[0] else 0,
            "end": words[-1]["end"] if "end" in words[-1] else 0,
            "text": seg_text,
            "words": words,
        }
        segments.append(seg)
    elif full_text:
        # No word timestamps — uniform distribution fallback
        text_words = full_text.split()
        dur = max(len(text_words) * 0.3, 1.0)  # ~300ms per word estimate
        w_dur = dur / max(len(text_words), 1)
        segments.append({
            "start": 0.0,
            "end": dur,
            "text": full_text,
            "words": [
                {"word": w, "start": i * w_dur, "end": (i + 1) * w_dur}
                for i, w in enumerate(text_words)
            ],
        })

    # Estimate duration from last word end
    duration = segments[0]["end"] if segments else None

    return {
        "text": full_text,
        "segments": segments,
        "duration": duration,
        "language": None,  # language is embedded in CLI output prefix
    }
