"""Diarization-Merge: Flicker-Segmente dürfen Wörter nicht zerhauen (Karaoke-Bug)."""
from __future__ import annotations

from app.service import _merge_diarization


def _seg(start: float, end: float, text: str, words: list) -> dict:
    return {"start": start, "end": end, "text": text, "words": words}


def _w(start: float, end: float, word: str) -> dict:
    return {"word": word, "start": start, "end": end}


def test_no_flicker_when_single_speaker_segments_adjacent():
    """Gleicher Sprecher, winzige Flicker-Grenzen → Wörter bleiben in einem Segment."""
    asr_segments = [
        _seg(0.0, 4.0, "Hallo Welt das ist ein Test",
             [_w(0.0, 0.4, "Hallo"), _w(0.4, 0.8, "Welt"),
              _w(0.8, 1.2, "das"), _w(1.2, 1.6, "ist"),
              _w(1.6, 2.0, "ein"), _w(2.0, 2.4, "Test")]),
    ]
    # pyannote-Flicker: viele winzige Segmente, alle SPEAKER_00
    diar = [
        {"start": 0.0, "end": 0.41, "speaker": "SPEAKER_00"},
        {"start": 0.41, "end": 0.82, "speaker": "SPEAKER_00"},
        {"start": 0.82, "end": 1.23, "speaker": "SPEAKER_00"},
        {"start": 1.23, "end": 1.64, "speaker": "SPEAKER_00"},
        {"start": 1.64, "end": 2.05, "speaker": "SPEAKER_00"},
        {"start": 2.05, "end": 2.5, "speaker": "SPEAKER_00"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    # Flicker-Segmente gleichen Sprechers werden zusammengefasst
    assert len(merged) == 1, f"erwartet 1 Segment, bekam {len(merged)}: {merged}"
    assert merged[0]["text"] == "Hallo Welt das ist ein Test"


def test_word_not_lost_at_segment_boundary():
    """Wort, dessen start kurz vor der Segmentgrenze liegt, geht nicht verloren."""
    asr_segments = [
        _seg(0.0, 2.0, "erster zweiter",
             [_w(0.0, 0.5, "erster"), _w(0.5, 1.0, "zweiter")]),
    ]
    diar = [
        {"start": 0.0, "end": 0.6, "speaker": "SPEAKER_00"},
        {"start": 0.6, "end": 1.2, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    texts = [m["text"] for m in merged]
    joined = " ".join(texts)
    assert "erster" in joined and "zweiter" in joined, f"Wörter verloren: {texts}"


def test_speaker_change_keeps_separation():
    """Echter Sprecherwechsel bleibt erhalten — nur Flicker wird gemerged."""
    asr_segments = [
        _seg(0.0, 4.0, "Hallo Welt Auf Wiedersehen",
             [_w(0.0, 0.5, "Hallo"), _w(0.5, 1.0, "Welt"),
              _w(2.0, 2.5, "Auf"), _w(2.5, 3.0, "Wiedersehen")]),
    ]
    diar = [
        {"start": 0.0, "end": 1.2, "speaker": "SPEAKER_00"},
        {"start": 2.0, "end": 3.2, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    assert len(merged) == 2
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[1]["speaker"] == "SPEAKER_01"
