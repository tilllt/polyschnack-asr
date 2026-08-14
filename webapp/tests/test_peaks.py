"""Peak-Berechnung (Waveform-Preview) — Streaming-Binning, kein ffmpeg nötig.

Regression 2026-08-14: die alte Implementierung materialisierte ALLE Samples
als Python-Tuple (`struct.unpack`) — 150-min-Audio ≈ 4,6 GB RAM + hartes
60-s-ffmpeg-Timeout → kaputte Waveform bei langen Dateien. Die Binning-Logik
ist jetzt eine pure Funktion (`peaks_from_s16le`), getestet ohne ffmpeg.
"""
from __future__ import annotations

import struct

import numpy as np

import app.peaks as peaks_mod
from app.peaks import PEAK_COUNT, peaks_from_s16le


def _s16le(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def test_peaks_konstante_amplitude_ergibt_eins():
    total = PEAK_COUNT * 8  # 8 Samples pro Bin
    raw = _s16le([32767] * total)
    peaks = peaks_from_s16le([raw], total)
    assert len(peaks) == PEAK_COUNT
    assert all(abs(p - 1.0) < 1e-6 for p in peaks)


def test_peaks_erster_bin_halbe_amplitude():
    total = PEAK_COUNT * 8
    samples = [0] * total
    samples[0:8] = [16384] * 8  # Bin 0 → 16384/32767 ≈ 0.500015
    peaks = peaks_from_s16le([_s16le(samples)], total)
    assert abs(peaks[0] - 0.5) < 1e-3
    assert all(abs(p) < 1e-6 for p in peaks[1:])


def test_peaks_chunked_gleich_einmal():
    """Mehrere s16le-Häppchen ergeben dasselbe Ergebnis wie ein Stück."""
    total = PEAK_COUNT * 8
    rng = np.random.default_rng(3)
    samples = rng.integers(-32768, 32767, total, dtype=np.int16)
    raw = samples.astype("<i2").tobytes()
    one = peaks_from_s16le([raw], total)

    chunk = 5000
    pieces = [raw[i:i + chunk * 2] for i in range(0, len(raw), chunk * 2)]
    many = peaks_from_s16le(pieces, total)
    assert one == many


def test_peaks_leere_chunks_und_kurze_audios():
    total = 1000  # kürzer als PEAK_COUNT
    peaks = peaks_from_s16le([_s16le([1000] * 1000), b""], total)
    assert len(peaks) == PEAK_COUNT
    assert all(0.0 <= p <= 1.0 for p in peaks)


def test_compute_peaks_ohne_ffmpeg_graceful(monkeypatch):
    """CI-Test-Container hat kein ffmpeg/ffprobe → [] statt Crash."""
    monkeypatch.setattr(peaks_mod, "probe_sample_count", lambda b: 16000)

    def _no_ffmpeg(*a, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(peaks_mod.sp, "Popen", _no_ffmpeg)
    assert peaks_mod.compute_peaks(b"whatever") == []


def test_probe_sample_count_fallback_ohne_ffprobe(monkeypatch):
    monkeypatch.setattr(peaks_mod.sp, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    n = peaks_mod.probe_sample_count(b"x" * 32000)
    assert n == 16000  # len/2
