"""Change 168 (User-Vorgabe): Wort-Invariante — jedes Wort hat ein Timing.

ensure_word_timings generiert fehlende start/end aus Nachbarn + geschätzter
Wortlänge; reconcile_words_to_text wendet es auf jedes Segment an.
"""
import pytest

from app.routers.segments import ensure_word_timings, reconcile_words_to_text


def _w(word, s=None, e=None):
    d = {"word": word}
    if s is not None:
        d["start"] = s
    if e is not None:
        d["end"] = e
    return d


# ------------------------------------------------------ Interpolation

def test_gap_between_anchors_proportional():
    words = [_w("a", 0.0, 1.0), _w("bb", None, None), _w("ccc", None, None), _w("dddd", 4.0, 5.0)]
    out = ensure_word_timings(words, 0.0, 6.0)
    # Lücke 1.0 → 4.0 = 3.0s über "bb"(2) + "ccc"(3) → 1.2s / 1.8s
    assert out[1]["start"] == pytest.approx(1.0)
    assert out[1]["end"] == pytest.approx(2.2)
    assert out[2]["start"] == pytest.approx(2.2)
    assert out[2]["end"] == pytest.approx(4.0)
    # Anker unangetastet
    assert out[0] == words[0]
    assert out[3] == words[3]


def test_leading_word_uses_segment_start():
    words = [_w("a", None, None), _w("b", 2.0, 3.0)]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[0]["start"] == pytest.approx(0.0)
    assert out[0]["end"] == pytest.approx(2.0)  # bis zum Anker


def test_trailing_word_uses_segment_end():
    words = [_w("a", 0.0, 1.0), _w("b", None, None)]
    out = ensure_word_timings(words, 0.0, 3.0)
    assert out[1]["start"] == pytest.approx(1.0)
    assert out[1]["end"] == pytest.approx(3.0)


def test_no_anchors_distributes_segment_duration():
    words = [_w("a"), _w("bb"), _w("ccc")]
    out = ensure_word_timings(words, 0.0, 6.0)
    # 6s über Längen 1+2+3=6 → 1s / 2s / 3s
    assert out[0]["start"] == pytest.approx(0.0)
    assert out[0]["end"] == pytest.approx(1.0)
    assert out[1]["start"] == pytest.approx(1.0)
    assert out[1]["end"] == pytest.approx(3.0)
    assert out[2]["start"] == pytest.approx(3.0)
    assert out[2]["end"] == pytest.approx(6.0)


def test_all_anchored_untouched():
    words = [_w("a", 0.0, 1.0), _w("b", 1.0, 2.0)]
    out = ensure_word_timings(words, 0.0, 2.0)
    assert out == words


def test_empty_words():
    assert ensure_word_timings([], 0.0, 1.0) == []


def test_missing_segment_bounds_fallback():
    words = [_w("a", None, None)]
    out = ensure_word_timings(words, None, None)
    assert out[0]["start"] == pytest.approx(0.0)
    assert out[0]["end"] == pytest.approx(1.0)  # s1 = s0 + 1.0


# ------------------------------------------------ Fallback-only (User-Vorgabe)

def test_never_overwrites_existing_start():
    """Wort mit echtem start, ohne end → end ergänzt (geschätzte Länge),
    der echte start bleibt UNANGETASTET."""
    words = [_w("a", 1.5, None), _w("b", 2.0, 2.5)]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[0]["start"] == pytest.approx(1.5)  # echt — bleibt
    assert out[0]["end"] > 1.5                     # ergänzt
    assert out[0]["end"] == pytest.approx(1.5 + 0.15)  # "a" kurz → Min-Dauer


def test_never_overwrites_existing_end():
    """Wort mit echtem end, ohne start → start ergänzt, end bleibt."""
    words = [_w("Wort", None, 3.0), _w("b", 1.0, 1.5)]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[0]["end"] == pytest.approx(3.0)  # echt — bleibt
    assert out[0]["start"] < 3.0
    assert out[0]["start"] == pytest.approx(3.0 - 0.36)  # "Wort" 4 Zeichen


def test_anchors_never_overwritten_by_interpolation():
    """Verankerte Wörter (Aligner/ASR/manuell) bleiben exakt — auch wenn
    sie zwischen zeitlosen Wörtern liegen."""
    words = [
        _w("a", 0.0, 1.0),      # Anker
        _w("x"),                # zeitlos
        _w("b", 2.0, 3.0),      # Anker
        _w("c", 3.0, 4.0),      # Anker
    ]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[0]["start"] == pytest.approx(0.0) and out[0]["end"] == pytest.approx(1.0)
    assert out[2]["start"] == pytest.approx(2.0) and out[2]["end"] == pytest.approx(3.0)
    assert out[3]["start"] == pytest.approx(3.0) and out[3]["end"] == pytest.approx(4.0)
    # nur das zeitlose Wort wurde gefüllt
    assert out[1]["start"] == pytest.approx(1.0)
    assert out[1]["end"] == pytest.approx(2.0)


def test_manual_timing_mode_values_untouched_by_reconcile():
    """Manueller Timing-Modus: User-gesetzte Wort-Zeiten (PATCH
    update_word_timing) überleben einen späteren replace_segments
    (reconcile_words_to_text) — nur zeitlose Wörter bekommen Fallbacks."""
    segs = [{
        "start": 0.0,
        "end": 10.0,
        "text": "Das Haus steht am Berg",
        "words": [
            _w("Das", 0.5, 0.9),        # manuell verschoben (Timing-Modus)
            _w("Haus", 1.2, 1.7),       # manuell verschoben
            _w("steht"),                # zeitlos → Fallback
            _w("am", 3.0, 3.4),         # Aligner
            _w("Berg", 3.4, 3.8),       # Aligner
        ],
    }]
    out = reconcile_words_to_text(segs)
    w = out[0]["words"]
    # Manuelle Werte unangetastet
    assert w[0]["start"] == pytest.approx(0.5) and w[0]["end"] == pytest.approx(0.9)
    assert w[1]["start"] == pytest.approx(1.2) and w[1]["end"] == pytest.approx(1.7)
    assert w[3]["start"] == pytest.approx(3.0) and w[3]["end"] == pytest.approx(3.4)
    assert w[4]["start"] == pytest.approx(3.4) and w[4]["end"] == pytest.approx(3.8)
    # Alle Wörter haben Timings (Invariante)
    for x in w:
        assert isinstance(x.get("start"), (int, float))
        assert isinstance(x.get("end"), (int, float))


# ---------------------------------------- Nachbar-Clamps (User-Vorgabe 2)

def test_estimated_end_never_past_next_word_start():
    """Geschätztes end wird auf den start des NÄCHSTEN Wortes gekappt —
    nie darüber hinaus (keine Überlappung)."""
    # "langer-Text" (7 Zeichen → 0.63s) würde 2.0+0.63=2.63 ergeben,
    # aber das nächste Wort startet bei 2.1 → end = 2.1
    words = [_w("langer-Text", 2.0, None), _w("b", 2.1, 2.5)]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[0]["end"] == pytest.approx(2.1)
    assert out[0]["start"] == pytest.approx(2.0)  # echt — bleibt


def test_estimated_start_never_before_previous_word_end():
    """Geschätzter start wird auf das end des VORIGEN Wortes angehoben —
    nie davor (keine Überlappung)."""
    # "langer-Text" (7 Zeichen → 0.63s) → start 3.0-0.63=2.37, aber das
    # vorige Wort endet bei 2.8 → start = 2.8
    words = [_w("a", 2.0, 2.8), _w("langer-Text", None, 3.0)]
    out = ensure_word_timings(words, 0.0, 5.0)
    assert out[1]["start"] == pytest.approx(2.8)
    assert out[1]["end"] == pytest.approx(3.0)  # echt — bleibt


def test_no_overlap_invariant_all_pairs():
    """Invariante über die ganze Liste: für jedes benachbarte Wortpaar
    gilt end₁ <= start₂ (keine Überlappung) — gemischt echte + zeitlose."""
    words = [
        _w("a", 0.0, 0.4),
        _w("bb", None, None),       # zeitlos → interpoliert
        _w("ccc", 0.9, 1.2),        # Anker
        _w("dddd", 1.2, None),      # halb: end ergänzt, gekappt
        _w("e", 1.5, 1.9),          # Anker (start 1.5 > dddd.end 1.5? ==)
        _w("f", None, None),        # zeitlos
        _w("g", 2.4, 2.8),          # Anker
    ]
    out = ensure_word_timings(words, 0.0, 4.0)
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        assert a["end"] <= b["start"], f"Überlappung {i}: {a} vs {b}"
    # alle haben Timings
    for x in out:
        assert isinstance(x.get("start"), (int, float))
        assert isinstance(x.get("end"), (int, float))


# ------------------------------------------------------ reconcile-Integration

def test_reconcile_ensures_all_word_timings():
    segs = [{
        "start": 0.0,
        "end": 3.0,
        "text": "Hallo Welt",
        "words": [_w("Hallo", 0.0, 1.0), _w("Welt")],  # "Welt" ohne Timing
    }]
    out = reconcile_words_to_text(segs)
    w = out[0]["words"]
    # Invariante (Change 168): JEDES Wort hat start+end im Segment-Bereich
    assert len(w) == 2
    for x in w:
        assert isinstance(x.get("start"), (int, float))
        assert isinstance(x.get("end"), (int, float))
        assert 0.0 <= x["start"] <= x["end"] <= 3.0
    # Anker "Hallo" bleibt unangetastet
    assert w[0]["start"] == pytest.approx(0.0)
    assert w[0]["end"] == pytest.approx(1.0)
