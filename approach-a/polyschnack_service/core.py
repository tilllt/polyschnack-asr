"""Shared transcription core.

Decode/chunk/infer/stitch logic factored out of routes so the sync endpoint,
the SSE streaming endpoint and the async job worker all share one code path.
Kept import-light (no dependency on routes) to avoid circular imports.
"""
from __future__ import annotations
import asyncio
import re
import time
from typing import Any, AsyncIterator, Dict, List, Tuple

import numpy as np

from .chunker import ChunkWindow, plan_chunks, slice_chunks
from .config import MAX_WINDOWS_IN_FLIGHT, TARGET_SR, logger

# Seam-dedup constants (achetronic seam.go: 3 frames x 80 ms = 240 ms tolerance,
# keep at most 3 tail words for comparison).
SEAM_TOLERANCE_S = 0.24
SEAM_MAX_WORDS = 3


def dedup_seam(prev_words: List[Dict[str, Any]], head_words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop head words that collide with the previous window's tail at a seam.

    A word is dropped when its start time is within SEAM_TOLERANCE_S of the
    start or end of any of the last SEAM_MAX_WORDS previous words. That single
    rule covers both failure modes from achetronic issue #18:
    - same text at (nearly) the same time: a duplicate ("to to") → drop it;
    - different text at (nearly) the same time: a collision → the previous
      window wins (its decoder is fully warmed up at the seam).
    """
    if not prev_words or not head_words:
        return list(head_words)
    tail = prev_words[-SEAM_MAX_WORDS:]
    survivors: List[Dict[str, Any]] = []
    for h in head_words:
        if any(
            abs(h.get("start", 0.0) - p.get("end", 0.0)) <= SEAM_TOLERANCE_S
            or abs(h.get("start", 0.0) - p.get("start", 0.0)) <= SEAM_TOLERANCE_S
            for p in tail
        ):
            continue
        survivors.append(h)
    return survivors


def _to_windows(windows_or_ranges) -> List[ChunkWindow]:
    """Normalize (start, end) tuples to full-coverage ChunkWindows (backwards compat)."""
    out: List[ChunkWindow] = []
    for w in windows_or_ranges:
        if isinstance(w, ChunkWindow):
            out.append(w)
        else:
            s, e = int(w[0]), int(w[1])
            out.append(ChunkWindow(s, e, s, e))
    return out


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("▁", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace(" '", "'")


def extract(result) -> Dict[str, Any]:
    """Convert an onnx_asr result (optionally with timestamps) into a plain dict."""
    text = clean_text(getattr(result, "text", str(result)))
    tokens = list(getattr(result, "tokens", []) or [])
    ts = list(getattr(result, "timestamps", []) or [])
    return {"text": text, "tokens": tokens, "timestamps": ts}


def _segment_from(info: Dict[str, Any], offset: float) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Build one absolute-timestamped segment (+ word list) from a chunk result."""
    starts = info["timestamps"]
    if starts:
        seg_start = starts[0] + offset
        seg_end = (starts[-1] if len(starts) > 1 else starts[0] + 0.1) + offset
    else:
        seg_start = offset
        seg_end = offset + 0.1
    words: List[Dict[str, Any]] = []
    current_word: dict | None = None
    for i, (tok, ts) in enumerate(zip(info["tokens"], starts)):
        is_new_word = "▁" in tok or current_word is None
        clean_tok = tok.replace("▁", "").strip()
        if not clean_tok:
            # "▁" as standalone token = word boundary
            if current_word is not None:
                word_end = ts + offset
                current_word["end"] = word_end
                words.append(current_word)
                current_word = None
            continue
        if is_new_word:
            if current_word is not None:
                word_end = ts + offset
                current_word["end"] = word_end
                words.append(current_word)
            current_word = {"start": ts + offset, "end": 0.0, "word": clean_tok}
        else:
            current_word["word"] += clean_tok
    # Close final word
    if current_word is not None:
        current_word["end"] = seg_end
        words.append(current_word)

    # Validation: check if ▁-based detection produced correct word boundaries
    # by joining words with spaces and comparing to the full text.
    # Models that put ▁ on every subword token produce words like
    # ["Hel","lo","wo","rld"] instead of ["Hello","world"]. When that
    # happens, fall back to smarter approaches.
    if words and not _words_match_text(words, info["text"]):
        # Try timestamp-gap detection (uses real token timestamps)
        has_any_wordbreak = any("▁" in tok for tok in info["tokens"])
        if not has_any_wordbreak:
            words = _segment_by_timestamp_gap(info, offset, seg_end)
        # If still wrong (e.g. ▁ on subwords), use text words + token timestamps
        if not _words_match_text(words, info["text"]):
            words = _segment_with_token_timestamps(info, offset, seg_start, seg_end)

    # Legacy fallback for empty-word case
    if not words and len(info["tokens"]) > 1:
        has_any_wordbreak = any("▁" in tok for tok in info["tokens"])
        if not has_any_wordbreak:
            words = _segment_by_timestamp_gap(info, offset, seg_end)
        if not words:
            words = _segment_with_token_timestamps(info, offset, seg_start, seg_end)

    segment = {"start": seg_start, "end": seg_end, "segment": info["text"], "words": words}
    return segment, words


def _words_match_text(words: List[Dict[str, Any]], text: str) -> bool:
    """Check if words joined with single spaces equal the full text."""
    if not words:
        return False
    reconstructed = " ".join(w["word"] for w in words)
    return reconstructed.strip() == text.strip()


def _segment_with_token_timestamps(
    info: Dict[str, Any], offset: float,
    seg_start: float, seg_end: float,
) -> List[Dict[str, Any]]:
    """Split text into words by whitespace; use ACTUAL token timestamps.

    Distributes tokens proportionally across text words, then uses each
    word's first token timestamp as start and the next word's first token
    timestamp as end. Preserves the model's per-token timing accuracy
    even when ▁-based grouping fails (e.g. ▁ on every subword).
    """
    text = info["text"].strip()
    if not text:
        return []

    text_words = text.split()
    if len(text_words) <= 1:
        return []

    starts = info["timestamps"]
    n_tokens = len(starts)
    n_words = len(text_words)
    if n_tokens < 2 or n_words < 2:
        return []

    words: List[Dict[str, Any]] = []
    for i, w in enumerate(text_words):
        # Proportionally distribute tokens across words
        first_tok = int(round(i * n_tokens / n_words))
        last_tok = int(round((i + 1) * n_tokens / n_words)) - 1
        last_tok = max(last_tok, first_tok)  # at least 1 token per word

        word_start = starts[first_tok] + offset

        if last_tok + 1 < n_tokens:
            word_end = starts[last_tok + 1] + offset
        else:
            word_end = seg_end

        words.append({"word": w, "start": word_start, "end": word_end})

    return words


# Threshold for timestamp-gap word detection (seconds)
_WORD_GAP_THRESHOLD = 0.08  # 80ms — typical inter-word pause


def _segment_by_timestamp_gap(
    info: Dict[str, Any], offset: float, seg_end: float
) -> List[Dict[str, Any]]:
    """Fallback: detect word boundaries by timestamp gaps between tokens.

    Used when the primary ▁-based detection fails (e.g. models that don't
    use SentencePiece's ▁ convention). A gap > WORD_GAP_THRESHOLD between
    consecutive token timestamps indicates a word boundary.
    """
    tokens = info["tokens"]
    starts = info["timestamps"]
    if not tokens or not starts or len(tokens) != len(starts):
        return []

    words: List[Dict[str, Any]] = []
    current_word: Dict[str, Any] | None = None

    for i, (tok, ts) in enumerate(zip(tokens, starts)):
        clean_tok = tok.replace("▁", "").strip()
        if not clean_tok:
            continue

        # Start a new word when:
        #   a) first token (no current word)
        #   b) gap from previous token exceeds threshold
        is_new = current_word is None
        if not is_new and i > 0:
            gap = ts - starts[i - 1]
            if gap > _WORD_GAP_THRESHOLD:
                word_end = ts + offset
                current_word["end"] = word_end
                words.append(current_word)
                current_word = None
                is_new = True

        if is_new:
            current_word = {"start": ts + offset, "end": 0.0, "word": clean_tok}
        else:
            current_word["word"] += clean_tok

    # Close final word
    if current_word is not None:
        current_word["end"] = seg_end
        words.append(current_word)

    return words


def stitch(windows_or_ranges, results: List[Any]) -> Dict[str, Any]:
    """Stitch per-window results into absolute-timestamped segments + full text.

    Accepts ChunkWindow objects (emit-filtered + seam-deduped, the achetronic
    long-audio path) or plain (start, end) sample tuples (legacy behaviour:
    every chunk is emitted fully).
    """
    windows = _to_windows(windows_or_ranges)
    all_segments: List[Dict[str, Any]] = []
    all_words: List[Dict[str, Any]] = []
    prev_words: List[Dict[str, Any]] = []
    for w, res in zip(windows, results):
        info = extract(res)
        if not info["text"]:
            continue
        offset = w.emit_start / TARGET_SR
        seg, words = _segment_from(info, offset)

        emit_start_s = w.emit_start / TARGET_SR
        emit_end_s = w.emit_end / TARGET_SR
        is_overlap_window = (w.start, w.end) != (w.emit_start, w.emit_end)
        if is_overlap_window:
            # Keep only words that start inside this window's owned region;
            # neighbours own the overlap on their side of the boundary.
            words = [wd for wd in words if emit_start_s <= wd["start"] < emit_end_s]
            # Clamp the last word's end to the seam: _segment_from sets a word's
            # end from the NEXT token's start, which may sit in the overlap and
            # would otherwise make the seam-dedup below drop a legit neighbour.
            if words and words[-1]["end"] > emit_end_s:
                words[-1]["end"] = emit_end_s
            # Safety net: drop words colliding with the previous window's tail.
            words = dedup_seam(prev_words, words)

        if not words:
            continue
        prev_words = words

        if is_overlap_window:
            seg_text = " ".join(wd["word"] for wd in words)
            seg = {
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "segment": seg_text,
                "words": words,
            }
        all_segments.append(seg)
        all_words.extend(words)
    full_text = " ".join(s["segment"] for s in all_segments)
    return {"segments": all_segments, "words": all_words, "text": full_text}


async def transcribe_wav(worker, wav: np.ndarray, model_name: str,
                         progress_callback=None) -> Dict[str, Any]:
    """Full transcription of an already-decoded waveform. Returns stitched dict
    with an added `duration` (seconds) and `chunks` count.

    Long audio is processed in overlapping windows (achetronic-style); each
    window's emit region is stitched gap-free and seams are deduplicated.

    VRAM-Fix (2026-08-14): die Fenster werden NICHT mehr alle auf einmal an
    den Worker geschickt (das ließ im BatchWorker bis zu
    MAX_BATCH_SIZE × Fenster-Audio in einem ORT-Lauf aktiv werden → CUDA OOM
    bei langen Dateien). MAX_WINDOWS_IN_FLIGHT (Default 1) begrenzt die
    gleichzeitigen Inferenzen pro Request: der VRAM-Bedarf ist damit konstant
    und unabhängig von der Dateilänge. Cross-Request-Batching des Workers
    bleibt unberührt.
    """
    duration = wav.size / TARGET_SR
    windows = plan_chunks(wav)
    pieces = slice_chunks(wav, windows)
    t1 = time.perf_counter()
    total = len(pieces)
    max_in_flight = max(1, MAX_WINDOWS_IN_FLIGHT)
    sem = asyncio.Semaphore(max_in_flight)

    async def _track():
        nonlocal done
        done += 1
        if progress_callback:
            await progress_callback(done, total)

    async def _submit(piece):
        async with sem:
            return await worker.submit(piece, model_name)

    done = 0
    # ensure_future → Task-Objekte mit add_done_callback (Progress-Tracking);
    # der Semaphor begrenzt, wie viele davon gleichzeitig wirklich rechnen.
    futures = [asyncio.ensure_future(_submit(p)) for p in pieces]
    for f in futures:
        f.add_done_callback(lambda _: asyncio.ensure_future(_track()))
    results = await asyncio.gather(*futures)
    infer_ms = (time.perf_counter() - t1) * 1000
    out = stitch(windows, results)
    out["duration"] = duration
    out["chunks"] = total
    logger.info("transcribe_wav model=%s dur=%.2fs chunks=%d infer=%.0fms "
                "(max_in_flight=%d)",
                model_name, duration, total, infer_ms, max_in_flight)
    return out


async def stream_wav(worker, wav: np.ndarray, model_name: str) -> AsyncIterator[Dict[str, Any]]:
    """Yield one partial-result dict per window, in order, as each finishes.

    Each yielded dict: {text, chunk_index, total_chunks, start, end, final}.
    Windows are submitted sequentially so partials arrive incrementally (the
    point of streaming) rather than all at once after a batched gather.
    """
    windows = plan_chunks(wav)
    pieces = slice_chunks(wav, windows)
    total = len(pieces)
    for idx, (w, piece) in enumerate(zip(windows, pieces)):
        res = await worker.submit(piece, model_name)
        info = extract(res)
        if not info["text"]:
            yield {
                "text": "",
                "chunk_index": idx,
                "total_chunks": total,
                "start": w.emit_start / TARGET_SR,
                "end": w.emit_end / TARGET_SR,
                "final": idx == total - 1,
            }
            continue
        seg, _words = _segment_from(info, w.emit_start / TARGET_SR)
        yield {
            "text": info["text"],
            "chunk_index": idx,
            "total_chunks": total,
            "start": seg["start"],
            "end": seg["end"],
            "final": idx == total - 1,
        }
