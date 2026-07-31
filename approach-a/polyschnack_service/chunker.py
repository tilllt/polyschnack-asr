"""Long-audio chunking: overlapping sliding windows with silence-aware seams.

Ported from achetronic/parakeet (v0.8.0, MIT/Apache-2.0) — see
`.hermes/plans/2026-07-31_220000-achetronic-long-audio-port.md`.

Instead of cutting hard at VAD silence (which splits words when no silence
exists — music, continuous speech), we slide a window of CHUNK_SECONDS with
CHUNK_OVERLAP_SECONDS of shared context between neighbours. The overlap gives
the encoder acoustic context and the decoder time to warm up. Ownership of the
overlap is split at a single boundary chosen by a cascade:

    1. Silero VAD  — centre of the longest silence run in the overlap
    2. Mel energy  — quietest smoothed frame (robust fallback, no model)
    3. Midpoint    — arithmetic midpoint (always decides)

Every mel/sample frame belongs to exactly one window's *emit* range, so the
tiling is gap-free: emit_end[i] == emit_start[i+1]. Words landing on a seam are
additionally deduplicated in core.dedup_seam.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from .config import (
    TARGET_SR,
    CHUNK_SECONDS,
    CHUNK_OVERLAP_SECONDS,
    VAD_THRESHOLD,
    VAD_MIN_SILENCE_MS,
    logger,
)

_vad_model = None  # lazy init


def _get_vad():
    global _vad_model
    if _vad_model is None:
        try:
            from silero_vad import load_silero_vad  # type: ignore
            _vad_model = load_silero_vad(onnx=True)
            logger.info("PolySchnack chunker: loaded Silero VAD for seam detection")
        except Exception as exc:
            logger.warning("Silero VAD unavailable (%s); falling back to energy VAD", exc)
            _vad_model = "energy"
    return _vad_model


# ---------------------------------------------------------------------------
# Window planning (achetronic planChunksWithBoundaries)
# ---------------------------------------------------------------------------
@dataclass
class ChunkWindow:
    """One sliding window over the waveform.

    start/end: acoustic context handed to the encoder (the whole window is
    transcribed). emit_start/emit_end: the owned region — only tokens/words
    inside are kept. Adjacent emit ranges tile the timeline with no gap.
    """

    start: int      # context start (sample, inclusive)
    end: int        # context end (sample, exclusive)
    emit_start: int  # owned region start (sample, inclusive)
    emit_end: int    # owned region end (sample, exclusive)


# Oracle signature: (wav, overlap_start, overlap_end, midpoint) -> (frame, ok)
Oracle = Callable[[Optional[np.ndarray], int, int, int], Tuple[int, bool]]


def plan_chunks_with_boundaries(
    total: int,
    chunk_samples: int,
    overlap_samples: int,
    wav: Optional[np.ndarray],
    oracle: Optional[Oracle] = None,
) -> List[ChunkWindow]:
    """Plan overlapping windows with gap-free emit tiling.

    chunk_samples > overlap_samples >= 0 and total > 0 required. A nil oracle
    (or one that declines) falls back to the arithmetic midpoint, which
    reproduces the pre-issue-#18 behaviour. Whatever the oracle returns, the
    boundary is clamped so the emit ranges still tile [0, total).
    """
    if total <= chunk_samples:
        return [ChunkWindow(0, total, 0, total)]

    stride = chunk_samples - overlap_samples
    windows: List[ChunkWindow] = []
    start = 0
    while start < total:
        end = min(start + chunk_samples, total)
        windows.append(ChunkWindow(start, end, 0, 0))
        if end == total:
            break
        start += stride

    prev_emit_end = 0
    for i, w in enumerate(windows):
        w.emit_start = prev_emit_end
        if i == len(windows) - 1:
            w.emit_end = total
            prev_emit_end = total
            continue

        overlap_start = windows[i + 1].start
        overlap_end = w.end
        midpoint = (overlap_start + overlap_end) // 2

        boundary = midpoint
        if oracle is not None:
            frame, ok = oracle(wav, overlap_start, overlap_end, midpoint)
            if ok:
                # Clamp into the legal overlap so tiling always holds.
                boundary = max(overlap_start, min(int(frame), overlap_end - 1))

        w.emit_end = boundary
        prev_emit_end = boundary
    return windows


# ---------------------------------------------------------------------------
# Boundary oracles (achetronic boundary.go)
# ---------------------------------------------------------------------------
def _midpoint_boundary(start: int, end: int, midpoint: int) -> Tuple[int, bool]:
    """Always decides — the terminal layer of the cascade."""
    return midpoint, True


def _frame_energies(wav: np.ndarray, frame_samples: int) -> np.ndarray:
    """RMS energy per frame (loudness proxy for the mel-energy oracle)."""
    n = wav.size // frame_samples
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    framed = wav[: n * frame_samples].reshape(n, frame_samples).astype(np.float64)
    return np.sqrt((framed * framed).mean(axis=1) + 1e-12)


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average (prefix-sum); width <= 1 returns input unchanged."""
    if window <= 1 or values.size == 0:
        return values
    half = window // 2
    out = np.empty_like(values)
    for i in range(values.size):
        lo, hi = max(0, i - half), min(values.size, i + half + 1)
        out[i] = values[lo:hi].mean()
    return out


def _mel_energy_boundary(wav: np.ndarray, start: int, end: int, midpoint: int) -> Tuple[int, bool]:
    """Split at the quietest smoothed 10 ms frame inside the overlap."""
    frame_samples = int(0.01 * TARGET_SR)  # 10 ms
    seg = wav[start:end]
    if seg.size < frame_samples:
        return midpoint, False
    energies = _frame_energies(seg, frame_samples)
    smoothed = _smooth(energies, 15)
    if smoothed.size == 0:
        return midpoint, False
    idx = int(np.argmin(smoothed))
    return start + idx * frame_samples, True


def _vad_boundary(wav: np.ndarray, start: int, end: int, midpoint: int) -> Tuple[int, bool]:
    """Split at the centre of the longest Silero-detected silence in the overlap.

    Falls back to an energy-based silence detector when Silero is unavailable.
    Returns (_, False) to fall through when no usable silence is found.
    """
    if wav is None or end <= start:
        return midpoint, False
    model = _get_vad()
    if model == "energy":
        return _vad_energy_boundary(wav, start, end, midpoint)
    try:
        from silero_vad import get_speech_timestamps  # type: ignore
        import torch  # silero-vad pulls torch even for onnx mode; lightweight here

        t = torch.from_numpy(np.ascontiguousarray(wav[start:end]))
        ts = get_speech_timestamps(
            t,
            model,
            sampling_rate=TARGET_SR,
            threshold=VAD_THRESHOLD,
            min_silence_duration_ms=max(200, int(VAD_MIN_SILENCE_MS / 2)),
            return_seconds=False,
        )
    except Exception:
        return _vad_energy_boundary(wav, start, end, midpoint)

    # Longest gap between speech spans (including leading/trailing silence).
    gaps: List[Tuple[int, int]] = []
    prev_end = 0
    for sp in ts:
        gaps.append((prev_end, int(sp["start"])))
        prev_end = int(sp["end"])
    gaps.append((prev_end, end - start))

    longest = max(gaps, key=lambda g: g[1] - g[0])
    if longest[1] - longest[0] < int(0.3 * TARGET_SR):  # < 300 ms silence
        return midpoint, False
    center = start + (longest[0] + longest[1]) // 2
    return int(center), True


def _vad_energy_boundary(wav: np.ndarray, start: int, end: int, midpoint: int) -> Tuple[int, bool]:
    """Energy fallback: centre of the longest below-threshold 20 ms run."""
    frame_samples = int(0.02 * TARGET_SR)  # 20 ms
    seg = wav[start:end]
    if seg.size < frame_samples:
        return midpoint, False
    energies = _frame_energies(seg, frame_samples)
    thr = max(1e-3, float(energies.mean()) * 0.4)
    below = energies < thr
    best_start, best_len = -1, 0
    run = -1
    for i, b in enumerate(below):
        if b:
            if run < 0:
                run = i
            if i - run + 1 > best_len:
                best_len, best_start = i - run + 1, run
        else:
            run = -1
    if best_start < 0 or best_len < 15:  # < 300 ms
        return midpoint, False
    center = best_start + (best_len - 1) // 2
    return start + center * frame_samples, True


def chain_boundary(wav: Optional[np.ndarray], start: int, end: int, midpoint: int) -> Tuple[int, bool]:
    """VAD -> mel-energy -> midpoint cascade. Always decides."""
    if wav is None:
        return midpoint, True
    for oracle in (_vad_boundary, _mel_energy_boundary, _midpoint_boundary):
        frame, ok = oracle(wav, start, end, midpoint)
        if ok:
            return frame, True
    return midpoint, True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def plan_chunks(wav: np.ndarray) -> List[ChunkWindow]:
    """Plan overlapping windows for a waveform, splitting seams on silence.

    Windows shorter than the chunk size keep their context; a short audio gets
    a single full-coverage window (no chunking overhead).
    """
    total = wav.size
    chunk_samples = int(CHUNK_SECONDS * TARGET_SR)
    overlap_samples = int(CHUNK_OVERLAP_SECONDS * TARGET_SR)
    if total <= chunk_samples:
        return [ChunkWindow(0, total, 0, total)]
    oracle: Oracle = lambda _w, s, e, m: chain_boundary(wav, s, e, m)
    return plan_chunks_with_boundaries(total, chunk_samples, overlap_samples, wav, oracle)


def slice_chunks(wav: np.ndarray, windows: List[ChunkWindow]) -> List[np.ndarray]:
    """Slice wav by window context ranges.

    Keeps a strict 1:1 correspondence with the input windows (silent windows
    are NOT skipped — stitch() skips empty results by text), because the
    emit-tiling invariant requires every window's result to line up.
    """
    return [wav[w.start:w.end].copy() for w in windows]
