"""Test that _parse_result correctly reads word timestamps from segments.

Validates:
- seg.words is populated from ASR response
- seg.words preserves {word, start, end} format
- Empty/missing words is handled
- All required keys (start, end, text, words) are present
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import pytest
from asr_client import _parse_result


def test_parse_result_passes_words_through():
    """Words in the ASR response segments are preserved in the output."""
    payload = {
        "text": "hello world",
        "duration": 2.5,
        "language": "english",
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "hello",
                "words": [
                    {"word": "hello", "start": 0.0, "end": 1.0},
                ],
            },
            {
                "start": 1.0,
                "end": 2.5,
                "text": "world",
                "words": [
                    {"word": "world", "start": 1.0, "end": 2.5},
                ],
            },
        ],
    }
    result = _parse_result(payload)
    assert len(result["segments"]) == 2
    for seg in result["segments"]:
        assert "words" in seg
        assert len(seg["words"]) == 1
        w = seg["words"][0]
        assert "word" in w
        assert "start" in w
        assert "end" in w


def test_parse_result_missing_words():
    """Missing/empty words in ASR response → empty list in output (not None)."""
    payload = {
        "text": "hello",
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "hello"},
            # no "words" key at all
        ],
    }
    result = _parse_result(payload)
    for seg in result["segments"]:
        assert "words" in seg
        assert seg["words"] == []


def test_parse_result_no_segments():
    """Empty or missing segments list → empty segments in output."""
    result = _parse_result({"text": ""})
    assert result["segments"] == []


def test_parse_result_text_from_segment_fallback():
    """If seg.text is missing, fall back to seg.segment."""
    payload = {
        "text": "hello",
        "segments": [
            {"start": 0.0, "end": 1.0, "segment": "hello", "words": []},
        ],
    }
    result = _parse_result(payload)
    assert result["segments"][0]["text"] == "hello"


def test_parse_result_fields():
    """Result has all required fields."""
    payload = {
        "text": "hello",
        "duration": 1.0,
        "language": "de",
        "segments": [],
    }
    result = _parse_result(payload)
    assert "text" in result
    assert "duration" in result
    assert "language" in result
    assert "segments" in result


def test_parse_result_word_format():
    """Word dict format matches what the frontend Segment type expects."""
    seg_raw = {
        "start": 0.0,
        "end": 1.0,
        "text": "hello world",
        "words": [
            {"word": "hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ],
    }
    payload = {"text": "hello world", "segments": [seg_raw]}
    result = _parse_result(payload)
    w = result["segments"][0]["words"][0]
    # Frontend expects: { word: string, start: number, end: number }
    assert isinstance(w["word"], str)
    assert isinstance(w["start"], (int, float))
    assert isinstance(w["end"], (int, float))
    assert not isinstance(w["word"], list)  # not array-of-tokens


def test_parse_result_segment_key_fallback():
    """Segment key 'segment' works the same as 'text'."""
    payload = {
        "text": "hello",
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "segment": "hello",
                "words": [{"word": "hello", "start": 0.0, "end": 0.5}],
            },
        ],
    }
    result = _parse_result(payload)
    assert result["segments"][0]["words"][0]["word"] == "hello"
