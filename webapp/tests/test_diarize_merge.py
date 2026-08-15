"""Regression: _merge_diarization darf keinen Text verlieren.

Wenn der Diar-Service nur einen Teil der Audio abdeckt (pyannote bricht
z.B. nach ~35 s ab), fallen Wörter außerhalb der Turns in kein Segment.
Vor dem Fix (2026-08-15) verschwanden sie aus der Segment-Liste —
Karaoke/Anzeige verloren Text, obwohl der Gesamttext vollständig war.
Jetzt werden sie ans letzte Segment angehängt.
"""
import pytest

from app.service import _merge_diarization


def _words(*pairs):
    return [{"word": w, "start": s, "end": e} for w, s, e in pairs]


def test_merge_keeps_words_outside_diar_segments():
    segs = [{
        "start": 0.0, "end": 180.0, "text": "a b c d",
        "words": _words(("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 2.0, 3.0), ("d", 3.0, 4.0)),
    }]
    # Diar-Service liefert NUR den Anfang (0–2 s, Speaker A)
    diar = [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}]

    merged = _merge_diarization(segs, diar)

    assert merged, "Merge darf nicht leer sein"
    assert len(merged) == 1
    # Wörter nach 2 s (c, d) dürfen NICHT verloren gehen
    words = [w["word"] for w in merged[0]["words"]]
    assert words == ["a", "b", "c", "d"], f"Data-Loss: {words}"
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[0]["end"] == 4.0


def test_merge_no_leftover_when_full_coverage():
    segs = [{
        "start": 0.0, "end": 10.0, "text": "a b",
        "words": _words(("a", 0.0, 1.0), ("b", 1.0, 2.0)),
    }]
    diar = [{"start": 0.0, "end": 2.0, "speaker": "A"}]
    merged = _merge_diarization(segs, diar)
    assert len(merged) == 1
    assert [w["word"] for w in merged[0]["words"]] == ["a", "b"]
    assert merged[0]["end"] == 2.0  # Segment-Ende bleibt das Diar-Ende


def test_merge_empty_diar_returns_nothing():
    # Kein Diarization-Ergebnis → kein Merge (Aufrufer behält ASR-Segmente)
    segs = [{
        "start": 0.0, "end": 5.0, "text": "x",
        "words": _words(("x", 0.0, 1.0)),
    }]
    assert _merge_diarization(segs, []) == []
