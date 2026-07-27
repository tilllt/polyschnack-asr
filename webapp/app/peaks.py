"""Waveform peak computation for WaveSurfer caching.

Computes a fixed-size float array (2000 samples) representing the peak
amplitude envelope of the audio.  WaveSurfer uses this to draw the waveform
instantly without re-decoding the audio file.
"""
from __future__ import annotations

import io
import logging
import struct
import subprocess as sp
from typing import List

log = logging.getLogger(__name__)

PEAK_COUNT = 2000
TARGET_SR = 16000  # all stored audio is 16 kHz mono WAV


def compute_peaks(audio_bytes: bytes) -> List[float]:
    """Compute a PEAK_COUNT-length peak envelope from *audio_bytes*.

    Returns a flat list of floats in [0, 1] suitable for WaveSurfer's
    ``peaks`` option.
    """
    # Decode to raw s16le via ffmpeg
    try:
        proc = sp.run(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error",
                "-i", "pipe:0",
                "-ac", "1", "-ar", str(TARGET_SR),
                "-f", "s16le",
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            log.warning("peaks: ffmpeg decode failed (rc=%d, %d bytes)", proc.returncode, len(proc.stdout))
            return []
    except Exception:
        log.exception("peaks: ffmpeg decode threw")
        return []

    raw = proc.stdout
    total_samples = len(raw) // 2  # 2 bytes per s16 sample
    if total_samples == 0:
        return []

    # Parse s16le samples
    samples = struct.unpack(f"<{total_samples}h", raw)  # tuple of ints

    # Bin into PEAK_COUNT buckets, take absolute max per bin
    peaks: List[float] = [0.0] * PEAK_COUNT
    samples_per_bin = max(1, total_samples // PEAK_COUNT)

    for i in range(PEAK_COUNT):
        start = i * samples_per_bin
        end = start + samples_per_bin
        if end > total_samples:
            end = total_samples
        if start >= total_samples:
            break
        # Max absolute value in this bin
        bin_max = max(abs(samples[s]) for s in range(start, end))
        peaks[i] = bin_max / 32767.0  # normalize to [0, 1]

    return peaks
