#!/usr/bin/env python3
"""VAD-Engines (Change 060/062) — einheitliches Interface.

Jede Engine: ``detect(wav16k_float32) -> (regions, elapsed_s)`` mit
``regions = [(start_s, end_s), ...]``. Läuft CPU-only; torch-basierte
Engines (humaware, speechbrain) benötigen ein torch-venv (siehe README).

Lizenz-Hinweis (Change 062): Engines mit inkompatiblen Lizenzen
(ten_vad: Agora-Klauseln; cobra: kommerziell; marble_net: NVIDIA-Lizenz)
sind NUR als Benchmark-Referenz gedacht — produktiv nutzbar sind
silero_onnx (MIT), webrtc (BSD), humaware (MIT), speechbrain (Apache),
fsmn_vad (Apache-2.0).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

SR = 16_000

HERE = Path(__file__).parent
ASSETS = HERE / "assets"


def _regions(probs: np.ndarray, num_samples: int, window: int,
             threshold: float, min_speech_ms: int = 250,
             min_silence_ms: int = 400, speech_pad_ms: int = 120) -> list[tuple[float, float]]:
    """Gemeinsame Region-Logik (silero-Semantik, wie webapp app/vad.py)."""
    min_speech = int(SR * min_speech_ms / 1000)
    min_silence = int(SR * min_silence_ms / 1000)
    pad = int(SR * speech_pad_ms / 1000)
    regions: list[list[int]] = []
    current: list[int] | None = None
    silence = 0
    for i, p in enumerate(probs):
        start = i * window
        end = start + window
        if p >= threshold:
            silence = 0
            if current is None:
                current = [start, end]
            else:
                current[1] = end
        else:
            silence += window
            if current is not None and silence >= min_silence:
                if current[1] - current[0] > min_speech:
                    regions.append(current)
                current = None
    if current is not None and current[1] - current[0] > min_speech:
        regions.append(current)
    out = []
    for r in regions:
        s = max(0, r[0] - pad)
        e = min(num_samples, r[1] + pad)
        if e > s:
            out.append((s / SR, e / SR))
    return out


# ── silero-onnx (MIT) — Webapp-Implementierung (app/vad.py-Semantik) ──────

def silero_onnx(wav: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    os.environ.setdefault("DATA_DIR", "/tmp/ps_vad_bench")
    sys.path.insert(0, str(HERE.parents[1] / "webapp"))
    from app.vad import _ensure_model, regions_from_probs, speech_probs, model_path
    _ensure_model()
    import onnxruntime as ort
    sess = ort.InferenceSession(str(model_path()), providers=["CPUExecutionProvider"])
    t0 = time.perf_counter()
    probs = speech_probs(wav, sess)
    elapsed = time.perf_counter() - t0
    regs = regions_from_probs(probs, wav.size)
    return [(r["start"], r["end"]) for r in regs], elapsed


# ── ten-vad (Agora-Klauseln, NUR Referenz) via sherpa-onnx ────────────────

def ten_vad(wav: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    import sherpa_onnx
    cfg = sherpa_onnx.VadModelConfig()
    cfg.ten_vad.model = str(ASSETS / "tenvad" / "ten-vad-sherpa.onnx")
    cfg.ten_vad.threshold = 0.5
    cfg.ten_vad.min_silence_duration = 0.4
    cfg.ten_vad.min_speech_duration = 0.25
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
    ws = cfg.ten_vad.window_size
    xl = wav.tolist()
    t0 = time.perf_counter()
    for i in range(0, len(xl), ws):
        vad.accept_waveform(xl[i:i + ws])
    elapsed = time.perf_counter() - t0
    for _ in range(0, 16000, ws):
        vad.accept_waveform([0.0] * ws)
    vad.empty()
    regs = []
    while not vad.empty():
        seg = vad.front
        regs.append((seg.start / SR, (seg.start + len(seg.samples)) / SR))
        vad.pop()
    return regs, elapsed


# ── webrtc (BSD) — GMM-Baseline ───────────────────────────────────────────

def webrtc(wav: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    import webrtcvad
    v = webrtcvad.Vad(2)  # Aggressiveness 2
    x16 = (np.clip(wav, -1, 1) * 32767).astype(np.int16)
    frame = 480  # 30 ms @ 16 kHz (webrtcvad erwartet 10/20/30 ms)
    n = x16.size // frame
    probs = np.zeros(n, dtype=np.float32)
    t0 = time.perf_counter()
    for i in range(n):
        try:
            probs[i] = 1.0 if v.is_speech(x16[i * frame:(i + 1) * frame].tobytes(), SR) else 0.0
        except Exception:
            probs[i] = 0.0
    elapsed = time.perf_counter() - t0
    return _regions(probs, x16.size, window=frame, threshold=0.5), elapsed


# ── humaware (MIT, torch) — Forschungs-Modell ─────────────────────────────

def humaware(wav: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    import torch
    model = torch.jit.load(str(ASSETS / "humaware" / "HumAwareVAD.jit"), map_location="cpu")
    model.eval()
    # Silero-v4-Semantik: exakt 512 Samples (16 kHz) pro Frame/Aufruf.
    # Batch-Forward (Modell ist batch-aware) — Einzel-Aufrufe wären ~15× RTF.
    win = 512
    n = wav.size // win
    t0 = time.perf_counter()
    probs = np.empty(n, dtype=np.float32)
    B = 512  # Chunks pro Batch
    with torch.no_grad():
        for start in range(0, n, B):
            end = min(start + B, n)
            batch = torch.from_numpy(
                wav[start * win:end * win].reshape(end - start, win)).float()
            out = model(batch, SR).reshape(-1)
            probs[start:end] = out[:end - start].numpy()
    elapsed = time.perf_counter() - t0
    return _regions(probs, wav.size, window=win, threshold=0.5), elapsed


# ── speechbrain-crdnn (Apache, EN-trainiert) ──────────────────────────────

def speechbrain(wav: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    import torch
    from speechbrain.inference.VAD import VAD
    vad = VAD.from_hparams(
        source="speechbrain/vad-crdnn-libriparty",
        savedir=os.path.expanduser("~/.cache/speechbrain"),
    )
    t0 = time.perf_counter()
    t = torch.from_numpy(wav).float().unsqueeze(0)  # [1, time]
    probs_t = vad.get_speech_prob_chunk(t)  # Tensor [1, T]
    elapsed = time.perf_counter() - t0
    p = probs_t.squeeze(0).numpy().astype(np.float32)
    win = int(SR * 0.030)  # CRDNN: 30 ms-Frames (speechbrain Model-Card)
    return _regions(p, wav.size, window=win, threshold=0.5), elapsed


# ── energy (deterministische Baseline) ────────────────────────────────────

def energy(wav: np.ndarray, window: int = 512, thresh_db: float = -40.0) -> tuple[list[tuple[float, float]], float]:
    """RMS-Energie-Baseline (deterministisch, kein ML)."""
    n = (wav.size - window) // window + 1
    probs = np.empty(n, dtype=np.float32)
    t0 = time.perf_counter()
    for i in range(n):
        seg = wav[i * window:(i + 1) * window]
        rms = float(np.sqrt((seg ** 2).mean()))
        probs[i] = 1.0 if rms > 10 ** (thresh_db / 20) else 0.0
    elapsed = time.perf_counter() - t0
    regs = _regions(probs, wav.size, window=window, threshold=0.5)
    return regs, elapsed


# ── Registry ──────────────────────────────────────────────────────────────

ENGINES = {
    "silero_onnx": silero_onnx,
    "ten_vad": ten_vad,
    "webrtc": webrtc,
    "humaware": humaware,
    "speechbrain": speechbrain,
    "energy": energy,
}

LICENSES = {
    "silero_onnx": "MIT — produktiv nutzbar",
    "ten_vad": "Apache-2.0 + Agora-Klauseln — NUR Referenz",
    "webrtc": "BSD — produktiv nutzbar (Baseline)",
    "humaware": "MIT — produktiv nutzbar (Forschung)",
    "speechbrain": "Apache-2.0 — produktiv nutzbar (EN-trainiert)",
    "energy": "— deterministische Baseline",
}
