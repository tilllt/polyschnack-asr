"""VRAM-Fix: transcribe_wav begrenzt gleichzeitige Fenster-Inferenzen.

Regression 2026-08-14: der Batch-Pfad schickte ALLE Chunk-Fenster auf einmal
an den BatchWorker → im GPU-Betrieb waren bis zu MAX_BATCH_SIZE × Fenster
gleichzeitig aktiv (CUDA OOM bei langen Dateien, z.B. 150-min-MP3 mit dem
alten 300-s-Default). Seit dem Fix skaliert der VRAM-Bedarf pro Request mit
der Fenstergröße, nicht mit der Dateilänge.
"""
from __future__ import annotations

import asyncio

import numpy as np

import polyschnack_service.core as core
from polyschnack_service.config import TARGET_SR


class _Result:
    def __init__(self, text: str = "x"):
        self.text = text


class _CountingWorker:
    """Fake-Worker, der die maximale Anzahl gleichzeitiger Inferenzen misst."""

    def __init__(self):
        self.current = 0
        self.peak = 0
        self.calls = 0

    async def submit(self, piece, model_name):
        self.current += 1
        self.peak = max(self.peak, self.current)
        self.calls += 1
        await asyncio.sleep(0.005)  # genug Zeit, dass der Semaphor greift
        self.current -= 1
        return _Result(text="x")


def _wav(seconds: int) -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.normal(0, 0.3, seconds * TARGET_SR).astype(np.float32)


def test_transcribe_wav_begrenzt_gleichzeitige_fenster(monkeypatch):
    """Mit MAX_WINDOWS_IN_FLIGHT=1 dürfen nie 2 Fenster gleichzeitig rechnen."""
    monkeypatch.setattr(core, "MAX_WINDOWS_IN_FLIGHT", 1)
    worker = _CountingWorker()

    out = asyncio.run(core.transcribe_wav(worker, _wav(600), "parakeet"))

    assert worker.calls == out["chunks"]  # alle Fenster verarbeitet
    assert out["chunks"] > 3  # 600 s bei 120-s-Fenstern → mehrere Fenster
    assert worker.peak <= 1  # Kern der Regression: nie parallel


def test_transcribe_wav_erlaubt_konfigurierte_parallelitaet(monkeypatch):
    """MAX_WINDOWS_IN_FLIGHT=2 lässt zwei Fenster gleichzeitig rechnen."""
    monkeypatch.setattr(core, "MAX_WINDOWS_IN_FLIGHT", 2)
    worker = _CountingWorker()

    out = asyncio.run(core.transcribe_wav(worker, _wav(600), "parakeet"))

    assert worker.calls == out["chunks"]
    assert worker.peak <= 2
    # Bei genug Fenstern sollte der Semaphor auch mal beide Slots nutzen —
    # das beweist, dass er NICHT fälschlich alles serialisiert.
    assert worker.peak >= 2 or out["chunks"] < 2


def test_chunk_default_120_sekunden():
    """Der neue CHUNK_SECONDS-Default (120) muss gelten — 300 s war die
    OOM-Ursache im Batch-Betrieb (in CI ist keine Env-Override gesetzt)."""
    from polyschnack_service import config as cfg

    assert cfg.CHUNK_SECONDS == 120.0
    assert cfg.MAX_WINDOWS_IN_FLIGHT == 1
