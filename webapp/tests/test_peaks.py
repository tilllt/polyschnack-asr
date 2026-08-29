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


def test_peaks_n_bins_feinere_aufloesung():
    """Change 155 (Timing-Zoom): n_bins-Parameter liefert exakt n_bins
    Werte; ein Signalwechsel wird in feineren Bins korrekt abgebildet."""
    total = 16000  # 1 s bei 16 kHz
    # Erste Hälfte leise, zweite Hälfte laut → Wechsel bei Bin 1000/2000
    samples = np.zeros(total, dtype=np.int16)
    samples[total // 2:] = 20000
    raw = samples.astype("<i2").tobytes()

    coarse = peaks_from_s16le([raw], total, n_bins=2000)
    assert len(coarse) == 2000
    assert coarse[999] < 0.05  # leise
    assert coarse[1000] > 0.5  # laut

    fine = peaks_from_s16le([raw], total, n_bins=8000)
    assert len(fine) == 8000
    assert fine[3999] < 0.05
    assert fine[4000] > 0.5


def test_compute_peaks_ohne_ffmpeg_graceful(monkeypatch):
    """CI-Test-Container hat kein ffmpeg/ffprobe → [] statt Crash."""
    monkeypatch.setattr(peaks_mod, "probe_sample_count", lambda b: 16000)

    def _no_ffmpeg(*a, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(peaks_mod.sp, "Popen", _no_ffmpeg)
    assert peaks_mod.compute_peaks(b"whatever") == []


def test_compute_peaks_path_ohne_ffmpeg_graceful(monkeypatch):
    """Pfad-Variante: kein ffmpeg → [] statt Crash (gleicher Fallback)."""
    monkeypatch.setattr(peaks_mod, "probe_sample_count_path", lambda p: 16000)

    def _no_ffmpeg(*a, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(peaks_mod.sp, "Popen", _no_ffmpeg)
    assert peaks_mod.compute_peaks_path(__import__("pathlib").Path("/tmp/x.mp3")) == []


def test_compute_peaks_path_ohne_probe_ergibt_leer(monkeypatch):
    """Kein ffprobe → keine Samples → [] ohne ffmpeg-Start überhaupt."""
    monkeypatch.setattr(peaks_mod, "probe_sample_count_path", lambda p: None)

    def _boom(*a, **k):
        raise AssertionError("Popen darf nicht aufgerufen werden")

    monkeypatch.setattr(peaks_mod.sp, "Popen", _boom)
    assert peaks_mod.compute_peaks_path(__import__("pathlib").Path("/tmp/x.mp3")) == []


def test_probe_sample_count_fallback_ohne_ffprobe(monkeypatch):
    monkeypatch.setattr(peaks_mod.sp, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    n = peaks_mod.probe_sample_count(b"x" * 32000)
    assert n == 16000  # len/2


def test_compute_preview_path_erzeugt_opus(tmp_path):
    """Change 096: Playback-Preview ist 24-kbps-Opus (statt 64-kbps-MP3).

    Die Preview wird nur fürs Browser-Playback gebraucht — die Welle kommt
    aus den Server-Peaks. Opus: ~2,9× kleiner + ~4× schnellerer Decode
    (decodeAudioData war der Lade-Flaschenhals: 26 s Desktop / 60–90 s
    Mobile bei 64-kbps-MP3). ffmpeg nötig → sonst skip (CI-Image hat es).
    """
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        import pytest

        pytest.skip("ffmpeg/ffprobe nicht verfügbar")

    src = tmp_path / "src.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-ar", "16000", "-ac", "1", str(src),
        ],
        check=True, capture_output=True,
    )

    out = peaks_mod.compute_preview_path(src)
    assert out is not None
    assert out.name == "src_preview.opus"
    assert out.exists() and out.stat().st_size > 0

    # Codec per ffprobe verifizieren (nicht nur Endung).
    p = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate",
            "-of", "csv=p=0", str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    codec, sr = p.stdout.strip().split(",")
    assert codec == "opus"
    # Opus-Dateien melden im Container IMMER 48000 (Opus-Spezifikation) —
    # die tatsächliche Bandbreite steckt im Stream; der Browser-Worker
    # rendert fürs Playback auf 16 kHz herunter (fetch.worker.ts).
    assert sr == "48000"

    # Idempotenz: zweiter Aufruf gibt denselben Pfad zurück (kein Re-encode).
    assert peaks_mod.compute_preview_path(src) == out
