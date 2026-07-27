"""Test that _segment_from() always returns words in segment dicts.

This validates the core invariant for karaoke:
- Every segment dict MUST contain a "words" key
- With valid timestamps: words list is non-empty with correct {word,start,end} format
- Without timestamps: words list is empty (but key still exists)
- stitch() propagates words through to the final result["segments"]

Two word-detection strategies are tested:
  1. Primary: SentencePiece ▁-marker detection
  2. Fallback: timestamp-gap detection (for models without ▁)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make approach-a importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from parakeet_service.core import _segment_from, stitch, _segment_by_timestamp_gap


class FakeResult:
    """Mimics the onnx_asr result object for extract()."""
    def __init__(self, text: str, tokens: list[str], timestamps: list[float]):
        self.text = text
        self.tokens = tokens
        self.timestamps = timestamps


# ---------------------------------------------------------------------------
# _segment_from tests — Primary ▁-based detection
# ---------------------------------------------------------------------------

def test_segment_from_has_words_key():
    """Segment dict MUST contain the 'words' key, even when empty."""
    info = {"text": "hello", "tokens": [], "timestamps": []}
    seg, words = _segment_from(info, 0.0)
    assert "words" in seg, "segment dict is missing 'words' key"
    assert words == [], "words should be empty when no timestamps"


def test_segment_from_produces_words_with_timestamps():
    """With valid timestamps, _segment_from returns a non-empty words list
    and the segment dict also contains the same words."""
    info = {
        "text": "hello world",
        "tokens": ["▁hello", "▁world"],
        "timestamps": [0.0, 1.5],
    }
    seg, words = _segment_from(info, 0.0)
    assert "words" in seg
    assert len(words) == 2
    assert len(seg["words"]) == 2
    # Each word has correct format
    for w in words:
        assert "word" in w
        assert "start" in w
        assert "end" in w
    assert words[0]["word"] == "hello"
    assert words[1]["word"] == "world"
    assert words[0]["start"] == 0.0
    assert words[1]["start"] == 1.5


def test_segment_from_offset_applied():
    """Offset is added to all timestamps."""
    info = {
        "text": "test",
        "tokens": ["▁test"],
        "timestamps": [10.0],
    }
    seg, words = _segment_from(info, 5.0)
    assert words[0]["start"] == 15.0  # 10 + 5


def test_segment_from_subword_merging():
    """Subword tokens (without ▁ prefix) are merged into the preceding word."""
    info = {
        "text": "Markus Söhne",
        "tokens": ["▁Mar", "kus", "▁Söh", "ne"],
        "timestamps": [0.0, 0.3, 1.0, 1.4],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 2
    assert words[0]["word"] == "Markus"
    assert words[1]["word"] == "Söhne"


def test_segment_from_skips_empty_tokens():
    """Pure-▁ tokens are skipped (not added as empty words)."""
    info = {
        "text": "a b",
        "tokens": ["▁a", "▁", "▁b"],
        "timestamps": [0.0, 0.5, 1.0],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 2
    assert words[0]["word"] == "a"
    assert words[1]["word"] == "b"


def test_segment_from_standalone_word_break_after_subword():
    """Standalone ▁ after a subword continuation token creates a word boundary.

    This catches the bug where ▁ as its own token was skipped without closing
    the previous word, merging consecutive words together (removing whitespace).
    E.g. tokens=["▁", "Hel", "lo", "▁", "world"] must produce ["Hello", "world"],
    not ["Helloworld"].
    """
    info = {
        "text": "Hello world",
        "tokens": ["▁", "Hel", "lo", "▁", "world"],
        "timestamps": [0.0, 0.1, 0.3, 1.0, 1.5],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 2, f"expected 2 words, got {len(words)}: {[w['word'] for w in words]}"
    assert words[0]["word"] == "Hello", f"word[0] should be 'Hello', got '{words[0]['word']}'"
    assert words[1]["word"] == "world", f"word[1] should be 'world', got '{words[1]['word']}'"
    # Timestamps should be correct
    assert words[0]["start"] == 0.1  # first non-▁ token's timestamp
    assert words[1]["start"] == 1.5  # "▁world" timestamp


def test_segment_from_no_tokens():
    """No tokens → empty words list."""
    info = {"text": "", "tokens": [], "timestamps": []}
    _, words = _segment_from(info, 0.0)
    assert words == []


def test_segment_from_word_end_times():
    """Word end times are set from the next word's start, or seg_end for last."""
    seg, words = _segment_from(
        {"text": "a b c", "tokens": ["▁a", "▁b", "▁c"], "timestamps": [0.0, 1.0, 2.0]},
        0.0,
    )
    assert len(words) == 3
    # Each word's end = next word's start (or seg_end for last)
    assert words[0]["end"] == pytest.approx(1.0)
    assert words[1]["end"] == pytest.approx(2.0)
    assert words[2]["end"] == seg["end"]


# ---------------------------------------------------------------------------
# _segment_from tests — Timestamp-gap fallback (models without ▁)
# ---------------------------------------------------------------------------

def test_no_wordbreak_marker_leading_space_tokens():
    """Tokens with leading spaces (but no ▁) use the timestamp-gap fallback."""
    info = {
        "text": "Hello world",
        "tokens": [" Hello", " world"],  # SentencePiece without ▁
        "timestamps": [0.0, 0.5],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 2, f"expected 2 words, got {len(words)}"
    assert words[0]["word"] == "Hello"
    assert words[1]["word"] == "World" or words[1]["word"] == "world"


def test_no_wordbreak_marker_bare_tokens():
    """Plain tokens without any whitespace markers use the timestamp-gap fallback."""
    info = {
        "text": "Hello world",
        "tokens": ["Hello", "world"],  # no ▁, no leading space
        "timestamps": [0.0, 0.5],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 2, f"expected 2 words, got {len(words)}"
    assert words[0]["word"] == "Hello"
    assert words[1]["word"] == "world"


def test_no_wordbreak_marker_subword_small_gap_stays_merged():
    """Subword tokens with small gaps stay merged (not falsely split)."""
    info = {
        "text": "Hello",
        "tokens": ["Hel", "lo"],       # subword, gap only 0.05s
        "timestamps": [0.0, 0.05],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 1, f"expected 1 merged word, got {len(words)}: {[w['word'] for w in words]}"
    assert words[0]["word"] == "Hello"


def test_no_wordbreak_marker_three_words():
    """Three bare tokens → three separate words with gap detection."""
    info = {
        "text": "how are you",
        "tokens": ["how", "are", "you"],
        "timestamps": [0.0, 0.5, 1.0],
    }
    _, words = _segment_from(info, 0.0)
    assert len(words) == 3, f"expected 3 words, got {len(words)}"
    assert words[0]["word"] == "how"
    assert words[1]["word"] == "are"
    assert words[2]["word"] == "you"


def test_fallback_timestamps_correct():
    """Timestamp-gap fallback produces correct per-word timestamps."""
    seg, words = _segment_from({
        "text": "Hello world",
        "tokens": ["Hello", "world"],
        "timestamps": [1.0, 2.0],
    }, 10.0)  # offset 10s
    assert len(words) == 2
    assert words[0]["start"] == 11.0  # 1.0 + 10
    assert words[0]["end"] == 12.0    # 2.0 + 10 (next word start)
    assert words[1]["start"] == 12.0  # 2.0 + 10
    assert words[1]["end"] == seg["end"]


# ---------------------------------------------------------------------------
# _segment_by_timestamp_gap direct tests
# ---------------------------------------------------------------------------

def test_gap_detection_produces_correct_words():
    """Direct test of _segment_by_timestamp_gap()."""
    words = _segment_by_timestamp_gap({
        "text": "hello world",
        "tokens": ["hello", "world"],
        "timestamps": [0.0, 0.5],
    }, 0.0, 1.0)
    assert len(words) == 2
    assert words[0]["word"] == "hello"
    assert words[1]["word"] == "world"


def test_gap_detection_merges_small_gaps():
    """Small gaps merge subword tokens."""
    words = _segment_by_timestamp_gap({
        "text": "Hello",
        "tokens": ["Hel", "lo"],
        "timestamps": [0.0, 0.03],  # 30ms < threshold
    }, 0.0, 1.0)
    assert len(words) == 1
    assert words[0]["word"] == "Hello"


def test_gap_detection_splits_large_gaps():
    """Large gaps split into separate words."""
    words = _segment_by_timestamp_gap({
        "text": "a b",
        "tokens": ["a", "b"],
        "timestamps": [0.0, 0.2],  # 200ms > threshold
    }, 0.0, 1.0)
    assert len(words) == 2
    assert words[0]["word"] == "a"
    assert words[1]["word"] == "b"


def test_gap_detection_empty_input():
    """Empty or mismatched input returns empty list."""
    assert _segment_by_timestamp_gap(
        {"text": "", "tokens": [], "timestamps": []}, 0.0, 1.0
    ) == []
    assert _segment_by_timestamp_gap(
        {"text": "a", "tokens": ["a"], "timestamps": []}, 0.0, 1.0
    ) == []  # len mismatch


# ---------------------------------------------------------------------------
# stitch tests
# ---------------------------------------------------------------------------

def test_stitch_preserves_words_in_segments():
    """stitch() must preserve the 'words' key in each segment of the result."""
    results = [
        FakeResult("hello", ["▁hello"], [0.0]),
        FakeResult("world", ["▁world"], [1.0]),
    ]
    # 1 second at 16kHz → 16000 samples per chunk
    ranges = [(0, 16000), (16000, 32000)]
    out = stitch(ranges, results)
    assert "segments" in out
    for idx, seg in enumerate(out["segments"]):
        assert "words" in seg, f"segment {idx} has no 'words' key"
        assert len(seg["words"]) > 0, f"segment {idx} has empty words"
    assert len(out["segments"]) == 2
    assert out["segments"][0]["words"][0]["word"] == "hello"
    assert out["segments"][1]["words"][0]["word"] == "world"


def test_stitch_top_level_words():
    """stitch() also returns a top-level 'words' list."""
    results = [FakeResult("hi", ["▁hi"], [0.0])]
    ranges = [(0, 16000)]
    out = stitch(ranges, results)
    assert "words" in out
    assert len(out["words"]) == 1


def test_stitch_empty_chunk():
    """A chunk with empty text is skipped by stitch()."""
    results = [
        FakeResult("hello", ["▁hello"], [0.0]),
        FakeResult("", [], []),   # empty → skip
        FakeResult("world", ["▁world"], [2.0]),
    ]
    ranges = [(0, 16000), (16000, 32000), (32000, 48000)]
    out = stitch(ranges, results)
    assert len(out["segments"]) == 2
