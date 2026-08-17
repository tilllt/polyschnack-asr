"""In-memory audio decoding & resampling.

Avoids per-chunk ffmpeg subprocesses. Strategy:
  * 16 kHz mono PCM WAV  -> read with stdlib `wave` straight to float32
  * Other WAV variants    -> stdlib `wave` + `audioop` (channels, sample width, rate)
  * Compressed / non-WAV  -> one ffmpeg subprocess decoding to s16le mono 16 kHz on stdout
"""
from __future__ import annotations
import audioop
import os
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from .config import TARGET_SR, logger


def _wav_info(data: bytes) -> Optional[dict]:
    try:
        with wave.open(BytesIO(data), "rb") as w:
            return {
                "frames": w.getnframes(),
                "sample_rate": w.getframerate(),
                "channels": w.getnchannels(),
                "sample_width": w.getsampwidth(),
                "compression": w.getcomptype(),
                "duration": (w.getnframes() / w.getframerate()) if w.getframerate() else 0.0,
            }
    except (wave.Error, EOFError, OSError):
        return None


def _decode_pcm_wav(data: bytes, info: dict) -> Optional[np.ndarray]:
    if info["compression"] != "NONE":
        return None
    sw = info["sample_width"]
    ch = info["channels"]
    if sw not in (1, 2, 3, 4) or ch not in (1, 2):
        return None
    try:
        with wave.open(BytesIO(data), "rb") as w:
            pcm = w.readframes(w.getnframes())
        if ch == 2:
            pcm = audioop.tomono(pcm, sw, 0.5, 0.5)
            ch = 1
        if info["sample_rate"] != TARGET_SR:
            pcm, _ = audioop.ratecv(pcm, sw, ch, info["sample_rate"], TARGET_SR, None)
        if sw == 1:
            return (np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        if sw == 2:
            return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if sw == 4:
            return np.frombuffer(pcm, dtype="<i4").astype(np.float32) / 2147483648.0
        pcm16 = audioop.lin2lin(pcm, sw, 2)
        return np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    except (wave.Error, EOFError, OSError, audioop.error, ValueError):
        return None


def _ffmpeg_decode(data: bytes) -> np.ndarray:
    """Decode any container/codec to mono 16 kHz float32 via ffmpeg.

    Zuerst über stdin-Pipe (schnell, kein Temp-File). Schlägt das fehl
    oder liefert 0 Samples, wird mit einer TEMP-DATEI wiederholt: Container
    wie M4A/MP4 mit moov-Atom am Dateiende (Signal-/Handy-Aufnahmen, 98 %
    der Datei = mdat) sind über eine nicht-seekbare Pipe nicht lesbar —
    ffmpeg meldet dann „partial file" und 0 Bytes, obwohl die Datei valide
    ist (Live-Befund 2026-08-17: „ValueError: empty audio" bei Signal-Audio).
    """
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1", "-ar", str(TARGET_SR),
        "-f", "s16le", "pipe:1",
    ]
    p = subprocess.run(cmd, input=data, capture_output=True, check=False)
    if p.returncode == 0 and p.stdout:
        return _s16le_to_float(p.stdout)

    # Fallback: seekbar via Temp-Datei (deckt MP4/M4A mit trailing moov ab).
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tf:
        tf.write(data)
        tmp_name = tf.name
    try:
        cmd2 = [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-i", tmp_name,
            "-ac", "1", "-ar", str(TARGET_SR),
            "-f", "s16le", "pipe:1",
        ]
        p2 = subprocess.run(cmd2, capture_output=True, check=False)
        if p2.returncode != 0:
            raise RuntimeError(
                f"ffmpeg decode failed: {p2.stderr.decode(errors='ignore')[:300]}"
            )
        if not p2.stdout:
            raise RuntimeError("ffmpeg decode failed: empty output")
        return _s16le_to_float(p2.stdout)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _s16le_to_float(pcm: bytes) -> np.ndarray:
    """s16le-Bytes → float32 [-1,1] (16-kHz-mono, wie vom ffmpeg-Pipe)."""
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def load_audio(data: bytes) -> np.ndarray:
    """Return mono float32 [-1,1] at 16 kHz."""
    info = _wav_info(data)
    if info is not None:
        wav = _decode_pcm_wav(data, info)
        if wav is not None:
            return wav
    return _ffmpeg_decode(data)


def reduce_noise(wav: np.ndarray) -> np.ndarray:
    """Apply spectral noise gating — removes stationary background noise."""
    try:
        import noisereduce as nr
        return nr.reduce_noise(y=wav, sr=TARGET_SR, stationary=True, prop_decrease=0.8)
    except Exception as exc:
        logger.warning("Noise reduction failed (%s), using original", exc)
        return wav


def load_audio_path(path: Path) -> np.ndarray:
    return load_audio(Path(path).read_bytes())
