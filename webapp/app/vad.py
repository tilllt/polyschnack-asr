"""Silero VAD pre-processing for the webapp backend.

Uses ONNX runtime (no PyTorch) to detect speech regions. Exposes:

- ``trim_silence(audio_bytes) -> bytes`` — trims leading/trailing silence
- ``detect_speech_regions(audio_bytes) -> list[dict]`` — returns VAD segments
"""
from __future__ import annotations

import io
import logging
import subprocess
import wave
from typing import Any, Dict, List

import numpy as np

TARGET_SR = 16_000
log = logging.getLogger(__name__)

_vad_model = None


def _get_vad():
    global _vad_model
    if _vad_model is not None:
        return _vad_model
    try:
        from silero_vad import load_silero_vad
        _vad_model = load_silero_vad(onnx=True)
        log.info("Loaded Silero VAD (ONNX)")
    except Exception:
        log.warning("Silero VAD unavailable — VAD preprocessing disabled")
        _vad_model = False
    return _vad_model


def _decode_to_wav(audio_bytes: bytes) -> np.ndarray:
    """Decode any audio to mono 16 kHz float32 [-1, 1] via ffmpeg."""
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1", "-ar", str(TARGET_SR),
        "-f", "s16le", "pipe:1",
    ]
    p = subprocess.run(cmd, input=audio_bytes, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {p.stderr.decode(errors='ignore')[:200]}")
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32767.0


def detect_speech_regions(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> List[Dict[str, Any]]:
    """Run VAD and return speech region dicts [{start, end}, ...] in seconds."""
    model = _get_vad()
    if not model:
        return []

    try:
        wav = _decode_to_wav(audio_bytes)
    except Exception:
        log.exception("audio decode failed in VAD")
        return []

    try:
        from silero_vad import get_speech_timestamps
        import torch
        t = torch.from_numpy(wav)
        ts = get_speech_timestamps(
            t, model,
            sampling_rate=TARGET_SR,
            threshold=threshold,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
            return_seconds=True,
        )
        return [{"start": s["start"], "end": s["end"]} for s in ts]
    except Exception:
        log.exception("VAD inference failed")
        return []


def trim_silence(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> bytes:
    """Remove leading/trailing silence. Returns trimmed WAV bytes."""
    regions = detect_speech_regions(audio_bytes, threshold, min_silence_ms, speech_pad_ms)
    if not regions:
        return audio_bytes

    wav = _decode_to_wav(audio_bytes)
    total = wav.size

    first_start = int(regions[0]["start"] * TARGET_SR)
    last_end = int(regions[-1]["end"] * TARGET_SR)

    if first_start <= 0 and last_end >= total:
        return audio_bytes

    trimmed = wav[first_start:last_end]
    s16 = (trimmed * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_SR)
        w.writeframes(s16)
    return buf.getvalue()
