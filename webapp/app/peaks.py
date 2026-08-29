"""Waveform peak computation for WaveSurfer caching.

Computes a fixed-size float array (2000 samples) representing the peak
amplitude envelope of the audio.  WaveSurfer uses this to draw the waveform
instantly without re-decoding the audio file.

VRAM/RAM-Fix (2026-08-14): die alte Implementierung materialisierte ALLE
Samples als Python-Tuple (``struct.unpack``) — bei 150-min-Audio sind das
~144 Mio. Samples ≈ 4,6 GB RAM, plus ein hartes 60-s-ffmpeg-Timeout →
kaputte Waveform bei langen Dateien. Jetzt wird der ffmpeg-Decode in
1-MiB-Häppchen gestreamt und pro Bin (2000 Bins) nur das Maximum aggregiert:
Speicher O(Chunk), Zeit O(n) mit numpy.

OOM-Fix (2026-08-14, 357-MB-/372-min-File): ``compute_peaks_path`` lässt
ffmpeg die Datei DIREKT von der Platte lesen (``-i <pfad>`` statt
``-i pipe:0`` + ``stdin.write``). Die Bytes-Variante schrieb das komplette
Audio erst in den RAM und dann in die stdin-Pipe — bei 357 MB blockierten
sich Python (stdin.write) und ffmpeg (stdout) gegenseitig (Deadlock) und
der peaks-Thread hielt parallel zum Transcribe-Worker ~1 GB RAM im 2-GB-
Container → OOM-Kill, „Broken pipe"-Flut, Job blieb auf processing.
"""
from __future__ import annotations

import logging
import subprocess as sp
import time
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

log = logging.getLogger(__name__)

PEAK_COUNT = 2000
TARGET_SR = 16000  # alle Peaks werden auf 16 kHz mono dekodiert
_CHUNK_BYTES = 1 << 20  # 1 MiB s16le pro Lese-Häppchen (~500k Samples)
_DECODE_TIMEOUT_S = 900  # 150-min-Audio dekodieren dauert > 60 s; seit 2026-08-14
# ist der Worker-Decode entfernt — nur noch der Hintergrund-Thread decodiert,
# deshalb grosszuegiger Puffer statt Race um die CPU.


def probe_sample_count(audio_bytes: bytes) -> Optional[int]:
    """Exakte Sample-Anzahl (16 kHz) via ffprobe — schnell, kein Voll-Decode.

    Fallback auf eine Größen-Schätzung, wenn ffprobe fehlt/fails (die
    Bin-Zuordnung darf dann leicht versetzt sein — für die Waveform egal).
    """
    try:
        proc = sp.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                "pipe:0",
            ],
            input=audio_bytes, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration_s = float(proc.stdout.strip())
            if duration_s > 0:
                return int(duration_s * TARGET_SR)
    except Exception:
        pass
    # Schätzung: s16-WAV wäre len/2 Samples; komprimiert ist die echte Anzahl
    # kleiner — die Bins werden dann etwas breiter, unkritisch fürs Rendern.
    return max(1, len(audio_bytes) // 2)


def probe_sample_count_path(path: Path) -> Optional[int]:
    """Sample-Anzahl via ffprobe direkt auf eine Datei (kein RAM-Objekt)."""
    try:
        proc = sp.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration_s = float(proc.stdout.strip())
            if duration_s > 0:
                return int(duration_s * TARGET_SR)
    except Exception:
        pass
    return None


def peaks_from_s16le(chunks: Iterable[bytes], total_samples: int, n_bins: int = PEAK_COUNT) -> List[float]:
    """Pure Binning-Logik über s16le-Häppchen (testbar ohne ffmpeg).

    *chunks* liefert Roh-Samples (little-endian int16, mono), *total_samples*
    die erwartete Gesamtzahl (bestimmt die Bin-Breite). Liefert exakt
    *n_bins* Float-Werte in [0, 1] (Default PEAK_COUNT = 2000).
    Change 155 (Timing-Zoom): n_bins ist der progressive-Peaks-Parameter —
    der Timing-Tab lädt bei Bedarf feinere Peaks (?length=N).
    """
    n_bins = max(1, int(n_bins))
    samples_per_bin = max(1, total_samples // n_bins)
    peaks = np.zeros(n_bins, dtype=np.float32)
    idx = 0
    for raw in chunks:
        if not raw:
            continue
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        n = arr.size
        if n == 0:
            continue
        bins = np.minimum((idx + np.arange(n)) // samples_per_bin, n_bins - 1)
        vals = np.abs(arr)
        changes = np.flatnonzero(np.diff(bins)) + 1
        starts = np.concatenate(([0], changes))
        ends = np.concatenate((changes, [n]))
        segmax = np.maximum.reduceat(vals, starts)
        np.maximum.at(peaks, bins[starts], segmax)
        idx += n
    return (peaks / 32767.0).tolist()


def compute_peaks(audio_bytes: bytes) -> List[float]:
    """Compute a PEAK_COUNT-length peak envelope from *audio_bytes*.

    Returns a flat list of floats in [0, 1] suitable for WaveSurfer's
    ``peaks`` option. Decodes JEDES ffmpeg-lesbare Format (MP3/OGG/WAV/…)
    in 1-MiB-Häppchen; Speicher bleibt konstant, egal wie lang das Audio ist.
    """
    total_samples = probe_sample_count(audio_bytes)
    if not total_samples:
        return []

    deadline = time.monotonic() + _DECODE_TIMEOUT_S
    try:
        proc = sp.Popen(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error",
                "-i", "pipe:0",
                "-ac", "1", "-ar", str(TARGET_SR),
                "-f", "s16le",
                "pipe:1",
            ],
            stdin=sp.PIPE, stdout=sp.PIPE,
        )
    except Exception:
        log.exception("peaks: ffmpeg start failed")
        return []

    def _chunks():
        assert proc.stdout is not None
        while True:
            if time.monotonic() > deadline:
                log.warning("peaks: decode timed out after %ds", _DECODE_TIMEOUT_S)
                return
            raw = proc.stdout.read(_CHUNK_BYTES)
            if not raw:
                return
            yield raw

    try:
        assert proc.stdin is not None
        proc.stdin.write(audio_bytes)
        proc.stdin.close()
        peaks = peaks_from_s16le(_chunks(), total_samples)
        proc.wait(timeout=30)
        if proc.returncode not in (0, None):
            log.warning("peaks: ffmpeg exit=%d — Peaks evtl. unvollständig",
                        proc.returncode)
        return peaks
    except BrokenPipeError:
        log.warning("peaks: ffmpeg beendete stdin vorzeitig (Decode-Fehler?)")
        return []
    except Exception:
        log.exception("peaks: compute threw")
        return []
    finally:
        if proc.poll() is None:
            proc.kill()


def compute_peaks_path(path: Path, n_bins: int = PEAK_COUNT) -> List[float]:
    """Wie :func:`compute_peaks`, aber ffmpeg liest die Datei direkt von der
    Platte (``-i <pfad>``) statt via ``pipe:0`` + ``stdin.write``.

    Für sehr große Dateien (357 MB / 372 min) — die Bytes-Variante lädt das
    komplette Audio in den RAM und blockiert beim Schreiben in die stdin-
    Pipe (Deadlock mit ffmpeg-stdout); das sprengte zusammen mit dem
    Transcribe-Worker das Container-RAM-Limit (OOM-Kill, „Broken pipe"-
    Flut, Job blieb auf processing). Der Pfad-Weg hält den Speicher konstant:
    ffmpeg streamt von Platte, Python liest stdout in 1-MiB-Häppchen.

    Change 155 (Timing-Zoom): n_bins = progressive Peaks (?length=N) —
    der Timing-Tab fordert beim Wort-Zoom feinere Peaks an.
    """
    total_samples = probe_sample_count_path(path)
    if not total_samples:
        return []

    deadline = time.monotonic() + _DECODE_TIMEOUT_S
    try:
        proc = sp.Popen(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error",
                "-i", str(path),
                "-ac", "1", "-ar", str(TARGET_SR),
                "-f", "s16le",
                "pipe:1",
            ],
            stdout=sp.PIPE,
        )
    except Exception:
        log.exception("peaks: ffmpeg start failed (path)")
        return []

    def _chunks():
        assert proc.stdout is not None
        while True:
            if time.monotonic() > deadline:
                log.warning("peaks: decode timed out after %ds", _DECODE_TIMEOUT_S)
                return
            raw = proc.stdout.read(_CHUNK_BYTES)
            if not raw:
                return
            yield raw

    try:
        peaks = peaks_from_s16le(_chunks(), total_samples, n_bins)
        proc.wait(timeout=30)
        if proc.returncode not in (0, None):
            log.warning("peaks: ffmpeg exit=%d — Peaks evtl. unvollständig",
                        proc.returncode)
        return peaks
    except Exception:
        log.exception("peaks: compute (path) threw")
        return []
    finally:
        if proc.poll() is None:
            proc.kill()


# Change 096: 24-kbps-Opus statt 64-kbps-MP3 — die Preview wird nur fürs
# Playback im Browser gebraucht (die Welle kommt aus den Server-Peaks).
# Netzlast 46 → ~17 MB bei 95 min; der Opus-Decode (libopus) ist ~4×
# schneller als MP3 — der eigentliche Flaschenhals war decodeAudioData
# (26 s Desktop / 60–90 s Mobile bei 64-kbps-MP3).
PREVIEW_BITRATE = "24k"
PREVIEW_SR = 16000


def compute_preview_path(src: Path) -> Optional[Path]:
    """Erzeugt eine schlanke Playback-Preview (64 kbps MP3, 16 kHz mono)
    NEBEN der Originaldatei: ``<stem>_preview.opus``.

    Wiedereinführung der Sidecar-Pipeline (2026-08-15): der Browser-Player
    lädt nur diese kleine Datei fürs Playback — WebAudio muss sonst die
    komplette WAV dekodieren (60 min = 60-380 MB, Play erst nach
    Minuten). Transkription läuft unverändert mit dem vollen Audio.

    Rückgabe: Pfad zur Preview, oder None bei Fehler/Timeout. Idempotent:
    existiert die Preview bereits, wird sie zurückgegeben ohne Neucodierung.
    """
    if src is None or not Path(src).exists():
        return None
    preview_p = Path(src).with_name(Path(src).stem + "_preview.opus")
    if preview_p.exists() and preview_p.stat().st_size > 0:
        return preview_p
    try:
        sp.run(
            [
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-i", str(src),
                "-c:a", "libopus", "-b:a", PREVIEW_BITRATE,
                "-ar", str(PREVIEW_SR), "-ac", "1",
                str(preview_p),
            ],
            capture_output=True, timeout=600, check=True,
        )
    except Exception:
        log.warning("preview: ffmpeg failed für %s", src, exc_info=True)
        preview_p.unlink(missing_ok=True)
        return None
    if preview_p.exists() and preview_p.stat().st_size > 0:
        return preview_p
    preview_p.unlink(missing_ok=True)
    return None
