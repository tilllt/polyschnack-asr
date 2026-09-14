"""Change 187: Wort-verankerte Segmentgrenzen — Tests der reinen Funktionen.

Fixtures spiegeln den Live-Fall (Recording 328): 8 Segmente, gedriftete
Grenzen, eine 14,5-s-Überlappung zwischen Segment 4 und 5.
"""
from __future__ import annotations

import copy

from app.word_anchors import (
    assign_words_by_index,
    enforce_word_anchored_bounds,
    glue_words_after,
    plan_bound_correction,
)


def _words(spec, t0=0.0, step=0.5):
    """Wortliste aus Text + gleichmäßigem Raster (start/end)."""
    out = []
    t = t0
    for w in spec.split():
        out.append({"word": w, "start": round(t, 3), "end": round(t + step * 0.8, 3)})
        t += step
    return out


def _seg(text, start, end, t0, step=0.5):
    return {
        "start": start,
        "end": end,
        "text": text,
        "words": _words(text, t0=t0, step=step),
    }


def test_grenzen_werden_aus_woertern_abgeleitet():
    segs = [
        _seg("eins zwei drei", 0.0, 99.0, t0=0.2),   # bewusst falsche Grenzen
        _seg("vier fünf", 100.0, 200.0, t0=2.0),
    ]
    out = enforce_word_anchored_bounds(copy.deepcopy(segs))
    assert out[0]["start"] == 0.2
    assert out[0]["end"] == 2.0          # Start des ersten Wortes von Segment 2
    assert out[1]["start"] == 2.0
    assert out[1]["end"] == out[1]["words"][-1]["end"]   # letztes Segment


def test_segment_ohne_woerter_bleibt_unangetastet():
    segs = [
        _seg("eins zwei", 0.0, 1.0, t0=0.2),
        {"start": 5.0, "end": 9.0, "text": "", "words": []},
    ]
    out = enforce_word_anchored_bounds(copy.deepcopy(segs))
    assert out[0]["end"] == out[0]["words"][-1]["end"]  # Folge ohne Wörter
    assert (out[1]["start"], out[1]["end"]) == (5.0, 9.0)


def test_ueberlappung_wird_aufgeloest_und_gemeldet():
    # Segment 4 endet 119.52, Segment 5 beginnt 105.00 (14,52 s Überlappung).
    a = _seg("eins zwei drei vier", 98.1, 119.52, t0=98.1, step=5.0)
    b = _seg("fünf sechs", 105.0, 129.87, t0=105.0, step=5.0)
    segs = [a, b]

    report = plan_bound_correction(segs)
    assert report["actionable"] is True
    assert report["overlaps"] and report["overlaps"][0]["overlap_s"] > 14.0
    assert report["shifted"][0]["segment"] == 1  # Segment 5 wird verschoben

    out = enforce_word_anchored_bounds(copy.deepcopy(segs))
    assert out[0]["end"] == out[1]["start"]              # lückenlos, keine Überlappung
    assert out[0]["end"] == a["words"][-1]["end"]        # Naht = Ende des letzten Wortes
    assert out[1]["words"][0]["start"] == out[0]["end"]  # Wortliste mitverschoben
    # interne Abstände der verschobenen Wörter bleiben erhalten
    assert out[1]["words"][1]["start"] - out[1]["words"][0]["start"] == 5.0


def test_pause_zwischen_segmenten_bleibt_erhalten():
    a = _seg("eins zwei", 0.0, 1.0, t0=0.0, step=1.0)     # endet 1.8
    b = _seg("drei vier", 4.0, 6.0, t0=4.0, step=1.0)     # beginnt nach Pause
    out = enforce_word_anchored_bounds(copy.deepcopy([a, b]))
    assert out[0]["end"] == 4.0                            # Grenze am Folgewort
    assert b["words"][0]["start"] == 4.0                   # Wortzeiten unangetastet
    assert out[1]["words"][0]["start"] == 4.0


def test_glue_words_after_schiebt_nur_rueckwaerts():
    words = _words("a b c", t0=10.0, step=1.0)
    out, delta = glue_words_after(12.0, words)
    assert delta == 2.0
    assert out[0]["start"] == 12.0
    assert out[2]["start"] == 14.0
    # nichts zu tun, wenn die Wörter schon hinter der Naht liegen
    out2, delta2 = glue_words_after(5.0, words)
    assert delta2 == 0.0 and out2[0]["start"] == 10.0


def test_assign_words_by_index_ordnet_nach_textreihenfolge():
    words = [{"word": f"w{i}", "start": float(i), "end": float(i) + 0.5} for i in range(6)]
    spans = [(0, 3), (1, 3)]
    out, err = assign_words_by_index(spans, words)
    assert err is None
    assert [w["word"] for w in out[0]] == ["w0", "w1", "w2"]
    assert [w["word"] for w in out[1]] == ["w3", "w4", "w5"]


def test_assign_words_by_index_meldet_mismatch_statt_zu_raten():
    words = [{"word": f"w{i}", "start": float(i), "end": float(i) + 0.5} for i in range(5)]
    out, err = assign_words_by_index([(0, 3), (1, 3)], words)
    assert err == "word_count_mismatch"
    assert out == {}


def test_assign_words_by_index_gechunktes_segment_sammelt_alle_chunks():
    words = [{"word": f"w{i}", "start": float(i), "end": float(i) + 0.5} for i in range(5)]
    out, err = assign_words_by_index([(0, 2), (0, 3)], words)
    assert err is None
    assert [w["word"] for w in out[0]] == ["w0", "w1", "w2", "w3", "w4"]


def test_live_fall_328_grenzen_aus_woertern():
    """8 Segmente wie in Produktion, Grenzen aus den Wortkanten abgeleitet."""
    counts = [33, 45, 42, 44, 78, 87, 48, 37]
    segs = []
    t = 0.24
    for i, n in enumerate(counts):
        text = " ".join(f"w{i}_{k}" for k in range(n))
        words = _words(text, t0=t, step=0.4)
        segs.append({"start": t - 5.0, "end": (words[-1]["end"] or 0) + 7.0,
                     "text": text, "words": words})
        t = words[-1]["end"] + 0.2
    report = plan_bound_correction(segs)
    assert report["with_words"] == 8
    assert report["actionable"] is True
    out = enforce_word_anchored_bounds(copy.deepcopy(segs))
    for idx, seg in enumerate(out):
        assert seg["start"] == seg["words"][0]["start"]
        if idx + 1 < len(out):
            assert seg["end"] == out[idx + 1]["start"]
        else:
            assert seg["end"] == seg["words"][-1]["end"]
    assert sum(len(s["words"]) for s in out) == sum(counts)


# --------------------------------------------------------------------------- #
# Change 190: Mindestdauer für Wortzeiten
# --------------------------------------------------------------------------- #
from app.word_anchors import enforce_min_word_durations, MIN_WORD_DURATION_S


def test_mindestdauer_hebt_null_dauer_an():
    """Live-Fall 328: Wort mit end == start (Segment 6, 'ist') bekommt >= 80 ms."""
    words = [
        {"word": "die", "start": 156.0, "end": 156.4},
        {"word": "ist", "start": 156.48, "end": 156.48},
        {"word": "verlinkt", "start": 156.48, "end": 156.8},
    ]
    out = enforce_min_word_durations(words)
    ist = out[1]
    assert ist["end"] - ist["start"] >= MIN_WORD_DURATION_S
    assert ist["start"] == 156.48          # Start bleibt
    assert out[0]["end"] == 156.4          # echte Dauer unangetastet
    # Monotonie: kein Wort beginnt vor dem Ende des Vorgängers
    for a, b in zip(out, out[1:]):
        assert b["start"] >= a["end"] - 1e-9


def test_mindestdauer_folgewort_am_gleichen_start():
    """Beide Wörter am selben Start: beide >= 80 ms, Kaskade statt Überlappung."""
    words = [
        {"word": "und", "start": 10.0, "end": 10.0},
        {"word": "das", "start": 10.0, "end": 10.0},
        {"word": "ist", "start": 10.0, "end": 10.0},
    ]
    out = enforce_min_word_durations(words)
    assert [round(w["end"] - w["start"], 3) for w in out] == [0.08, 0.08, 0.08]
    assert out[0]["end"] == 10.08 and out[1]["start"] == 10.08
    assert out[1]["end"] == 10.16 and out[2]["start"] == 10.16


def test_mindestdauer_laesst_lange_woerter_unveraendert():
    words = [{"word": "Weltprinzipien", "start": 13.0, "end": 14.2}]
    out = enforce_min_word_durations(words)
    assert out[0] == {"word": "Weltprinzipien", "start": 13.0, "end": 14.2}


def test_mindestdauer_begrenzt_auf_segmentende_aber_nie_unter_floor():
    words = [{"word": "Ende", "start": 9.95, "end": 9.95}]
    out = enforce_min_word_durations(words, seg_end=9.97)
    assert out[0]["end"] - out[0]["start"] >= MIN_WORD_DURATION_S
    assert out[0]["end"] >= 10.03


def test_mindestdauer_erzeugt_keine_ueberlappung_bei_engem_raster():
    """48 Wörter in 4,5 s (komprimiertes Segment 6) bleiben monoton."""
    words = [{"word": f"w{i}", "start": 153.0 + i * 0.02, "end": 153.0 + i * 0.02} for i in range(48)]
    out = enforce_min_word_durations(words)
    assert all(w["end"] - w["start"] >= MIN_WORD_DURATION_S - 1e-9 for w in out)
    for a, b in zip(out, out[1:]):
        assert b["start"] >= a["end"] - 1e-9
