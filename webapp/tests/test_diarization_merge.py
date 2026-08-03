"""Diarization-Merge: Flicker-Segmente dürfen Wörter nicht zerhauen (Karaoke-Bug)."""
from __future__ import annotations

import pytest

from app.service import _build_word_stream, _merge_diarization, _normalize_ts


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


def test_first_word_of_new_speaker_goes_to_new_speaker():
    """Wort beginnt 0.1s VOR d_start der neuen Sprecher-Grenze, endet aber darin.

    pyannote-Segmentgrenzen liegen oft knapp NACH dem letzten Wort-Ende des
    Vorgängers — das erste Wort des neuen Sprechers beginnt dann minimal vor
    d_start. Strikte start-Fenster-Zuordnung würde es dem ALTEN Speaker
    zuordnen (gemeldeter Bug). Overlap-Zuordnung muss es dem NEUEN geben.
    """
    asr_segments = [
        _seg(0.0, 4.0, "hallo welt test",
             [_w(0.0, 0.8, "hallo"), _w(0.8, 1.9, "welt"),
              _w(1.9, 2.6, "test")]),  # beginnt vor 2.0, endet danach
    ]
    diar = [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
        {"start": 2.0, "end": 4.0, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    assert len(merged) == 2, f"erwartet 2 Segmente, bekam {len(merged)}: {merged}"
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[0]["text"] == "hallo welt", merged[0]["text"]
    assert merged[1]["speaker"] == "SPEAKER_01"
    assert merged[1]["text"] == "test", merged[1]["text"]


def test_word_in_gap_goes_to_next_segment():
    """Wort liegt komplett in Lücke zwischen Segmenten → nächstem Segment zuordnen."""
    asr_segments = [
        _seg(0.0, 3.0, "a b",
             [_w(0.0, 0.9, "a"), _w(1.5, 2.2, "b")]),
    ]
    diar = [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
        {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    assert merged[1]["speaker"] == "SPEAKER_01"
    assert merged[1]["text"] == "b", merged[1]["text"]


def test_word_overlapping_two_segments_equally_goes_to_later():
    """Gleichstand bei Overlap → späteres Segment (neuer Sprecher gewinnt)."""
    asr_segments = [
        _seg(0.0, 3.0, "x y",
             [_w(0.0, 0.5, "x"), _w(1.75, 2.25, "y")]),  # y überlappt 1.75-2.0 und 2.0-2.25
    ]
    diar = [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
        {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization(asr_segments, diar)
    assert merged[1]["speaker"] == "SPEAKER_01"
    assert merged[1]["text"] == "y", merged[1]["text"]


# ---------------------------------------------------------------------------
# Wort-Stream-Normalisierer (Plan 2026-08-02, Task 1)
# ---------------------------------------------------------------------------
def test_normalize_ts_seconds():
    assert _normalize_ts(1.5, "s") == 1.5
    assert _normalize_ts(1500, "ms") == 1.5
    assert _normalize_ts(None, "s") is None
    assert _normalize_ts("2.5", "s") == 2.5


def test_build_word_stream_word_ts():
    segs = [{"start": 0.0, "end": 2.0, "text": "a b",
             "words": [{"word": "a", "start": 0.0, "end": 1.0},
                        {"word": "b", "start": 1.0, "end": 2.0}]}]
    ws = _build_word_stream(segs, 2.0)
    assert ws == [{"word": "a", "start": 0.0, "end": 1.0},
                  {"word": "b", "start": 1.0, "end": 2.0}]


def test_build_word_stream_segment_ts_only():
    """Keine Wort-TS: Text-Wörter uniform über das Segment verteilen."""
    segs = [{"start": 0.0, "end": 4.0, "text": "a b"}]
    ws = _build_word_stream(segs, 4.0)
    assert len(ws) == 2
    assert ws[0]["start"] == 0.0
    assert ws[1]["end"] == 4.0
    assert ws[0]["start"] < ws[1]["start"]


def test_build_word_stream_no_ts_returns_none():
    """Weder Wort- noch Segment-TS → None (kein Mapping möglich)."""
    segs = [{"text": "a b c"}]
    assert _build_word_stream(segs, None) is None


def test_build_word_stream_ms_fields():
    """Backend liefert start_ms/end_ms → in Sekunden normalisieren."""
    segs = [{"start_ms": 0, "end_ms": 2000, "text": "a",
             "words": [{"word": "a", "start_ms": 0, "end_ms": 2000}]}]
    ws = _build_word_stream(segs, 2.0)
    assert ws[0]["start"] == 0.0 and ws[0]["end"] == 2.0


# ---------------------------------------------------------------------------
# Proportionaler Fallback (Plan 2026-08-02, Task 2 — Status B)
# ---------------------------------------------------------------------------
def test_merge_diarization_no_word_stream_proportional():
    """Ohne Wort-Stream: Gesamttext proportional nach Segmentdauer aufteilen,
    Segmente mit estimated=True kennzeichnen."""
    diar = [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
        {"start": 2.0, "end": 10.0, "speaker": "SPEAKER_01"},
    ]
    merged = _merge_diarization([], diar, None, 10.0,
                                full_text="Hallo du bist dran und jetzt rede ich")
    assert len(merged) == 2
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[0].get("estimated") is True
    # Anteil: 2s/10s von 7 Wörtern ≈ 1-2 Wörter
    assert len(merged[0]["words"]) <= 2
    assert merged[1]["speaker"] == "SPEAKER_01"


def test_merge_diarization_ms_word_stream():
    """Wort-Stream mit ms-Feldern wird korrekt gemappt."""
    ws = [{"word": "Hallo", "start": 0.0, "end": 0.5},
          {"word": "hier", "start": 0.5, "end": 1.0}]
    diar = [{"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"}]
    merged = _merge_diarization([], diar, ws, 4.0)
    assert merged[0]["text"] == "Hallo hier"


def test_merge_diarization_no_stream_no_text_returns_empty():
    assert _merge_diarization([], [{"start": 0, "end": 1, "speaker": "S"}],
                              None, 1.0) == []
