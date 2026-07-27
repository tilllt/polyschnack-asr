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

from .chunker import auto_chunk, slice_chunks
from .config import TARGET_SR, logger


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
    segment = {"start": seg_start, "end": seg_end, "segment": info["text"], "words": words}
    return segment, words


def stitch(ranges: List[Tuple[int, int]], results: List[Any]) -> Dict[str, Any]:
    """Stitch per-chunk results into absolute-timestamped segments + full text."""
    all_segments: List[Dict[str, Any]] = []
    all_words: List[Dict[str, Any]] = []
    for (start_s, _end_s), res in zip(ranges, results):
        offset = start_s / TARGET_SR
        info = extract(res)
        if not info["text"]:
            continue
        seg, words = _segment_from(info, offset)
        all_segments.append(seg)
        all_words.extend(words)
    full_text = " ".join(s["segment"] for s in all_segments)
    return {"segments": all_segments, "words": all_words, "text": full_text}


async def transcribe_wav(worker, wav: np.ndarray, model_name: str,
                         progress_callback=None) -> Dict[str, Any]:
    """Full transcription of an already-decoded waveform. Returns stitched dict
    with an added `duration` (seconds) and `chunks` count.

    If *progress_callback* is given, it is called after each chunk finishes
    as `progress_callback(done: int, total: int)`.
    """
    duration = wav.size / TARGET_SR
    ranges = auto_chunk(wav)
    pieces = slice_chunks(wav, ranges)
    t1 = time.perf_counter()
    total = len(pieces)

    async def _track():
        nonlocal done
        done += 1
        if progress_callback:
            await progress_callback(done, total)

    done = 0
    # Use ensure_future so we get Task objects with add_done_callback
    futures = [asyncio.ensure_future(worker.submit(p, model_name)) for p in pieces]
    for f in futures:
        f.add_done_callback(lambda _: asyncio.ensure_future(_track()))
    results = await asyncio.gather(*futures)
    infer_ms = (time.perf_counter() - t1) * 1000
    out = stitch(ranges, results)
    out["duration"] = duration
    out["chunks"] = total
    logger.info("transcribe_wav model=%s dur=%.2fs chunks=%d infer=%.0fms",
                model_name, duration, total, infer_ms)
    return out


async def stream_wav(worker, wav: np.ndarray, model_name: str) -> AsyncIterator[Dict[str, Any]]:
    """Yield one partial-result dict per VAD chunk, in order, as each finishes.

    Each yielded dict: {text, chunk_index, total_chunks, start, end, final}.
    Chunks are submitted sequentially so partials arrive incrementally (the point
    of streaming) rather than all at once after a batched gather.
    """
    ranges = auto_chunk(wav)
    pieces = slice_chunks(wav, ranges)
    total = len(pieces)
    for idx, ((start_s, _end_s), piece) in enumerate(zip(ranges, pieces)):
        offset = start_s / TARGET_SR
        res = await worker.submit(piece, model_name)
        info = extract(res)
        seg, _words = _segment_from(info, offset)
        yield {
            "text": info["text"],
            "chunk_index": idx,
            "total_chunks": total,
            "start": seg["start"],
            "end": seg["end"],
            "final": idx == total - 1,
        }
