"""Change 140 (Wurzel-Fix): Text/Wort-Invariante.

reconcile_words_to_text gleicht die Wortliste per LCS an den Segment-Text
an: unveränderte Wörter behalten ihre (Aligner-)Zeiten, fehlende
Text-Wörter werden interpoliert, Fremdwörter entfernt. Der TEXT ist
unantastbar — nichts wird verschluckt (User-Befund ec98bfdf: 8/28
Segmente mit Desync; Export/Anzeige unvollständig).
"""
from app.routers.segments import reconcile_words_to_text


def _word(w: str, s: float, e: float) -> dict:
    return {"word": w, "start": s, "end": e}


def test_reconcile_removes_foreign_words_keeps_text():
    """Wörter ⊃ Text (Seg 0 ec98bfdf: „Herr Neulner zurück?" nur in den
    Wörtern): Fremdwörter werden entfernt, Matches behalten Zeiten,
    der Text bleibt unverändert."""
    seg = {
        "start": 5.12,
        "end": 15.41,
        "text": "Guten Tag hier ist Till",
        "words": [
            _word("Herr", 5.12, 5.28),
            _word("Neulner", 5.36, 5.68),
            _word("zurück?", 6.32, 6.48),
            _word("Guten", 6.48, 6.72),
            _word("Tag", 6.88, 7.04),
            _word("hier", 7.20, 7.40),
            _word("ist", 7.50, 7.70),
            _word("Till", 7.80, 8.00),
        ],
    }
    out = reconcile_words_to_text([seg])[0]
    joined = " ".join(w["word"] for w in out["words"])
    assert joined == seg["text"]  # Invariante: join(words) == text
    assert seg["text"] == "Guten Tag hier ist Till"  # Text unantastbar
    # Matches behalten ihre Aligner-Zeiten
    guten = out["words"][0]
    assert guten["word"] == "Guten" and guten["start"] == 6.48 and guten["end"] == 6.72


def test_reconcile_interpolates_missing_text_words():
    """Text ⊃ Wörter (Seg 6/7 ec98bfdf: Text 1113 vs Wörter 202): die
    fehlenden Text-Wörter werden ergänzt, Gesamttext exakt erhalten."""
    seg = {
        "start": 0.0,
        "end": 12.0,
        "text": "eins zwei drei vier fünf sechs",
        "words": [_word("eins", 0.0, 2.0), _word("fünf", 8.0, 10.0)],
    }
    out = reconcile_words_to_text([seg])[0]
    joined = " ".join(w["word"] for w in out["words"])
    assert joined == seg["text"]
    assert [w["word"] for w in out["words"]] == ["eins", "zwei", "drei", "vier", "fünf", "sechs"]
    # Matches behalten ihre Zeiten, Ergänzte liegen dazwischen (chronologisch)
    assert out["words"][0]["start"] == 0.0
    assert out["words"][4]["start"] == 8.0
    times = [w["start"] for w in out["words"]]
    assert times == sorted(times)


def test_reconcile_consistent_segment_unchanged():
    """Konsistentes Segment (join(words) == text) → 1:1, nichts ändert sich."""
    seg = {
        "start": 0.0,
        "end": 3.0,
        "text": "a b c",
        "words": [_word("a", 0.0, 1.0), _word("b", 1.0, 2.0), _word("c", 2.0, 3.0)],
    }
    out = reconcile_words_to_text([seg])[0]
    assert out["words"] == seg["words"]


def test_reconcile_keeps_override_flags():
    """Manuell korrigierte Wörter (override, Change 137) behalten ihr Flag
    über das Reconcile (1:1-Match)."""
    seg = {
        "start": 0.0,
        "end": 2.0,
        "text": "Hallo Welt",
        "words": [
            _word("Hallo", 0.0, 1.0),
            {**_word("Welt", 1.0, 2.0), "override": True},
        ],
    }
    out = reconcile_words_to_text([seg])[0]
    assert out["words"][1]["override"] is True
    assert out["words"][1]["start"] == 1.0


def test_reconcile_skips_segments_without_words_or_text():
    segs = [
        {"start": 0, "end": 1, "text": "nur text"},
        {"start": 1, "end": 2, "words": [_word("x", 1, 2)]},
    ]
    out = reconcile_words_to_text(segs)
    assert out[0] == segs[0]
    assert out[1] == segs[1]


def test_reconcile_leaves_consistent_words_untouched():
    """Change 160 (User-Regel): Ein konsistentes Segment (text ==
    join(words)) — wie beim reinen Grenz-Drag — wird von reconcile ohne
    Zeit-Änderung durchgereicht: jedes Wort behält start/end exakt.
    Der Drag fasst Wort-Timings nie an."""
    words = [
        _word("Das", 0.0, 0.4),
        _word("ist", 0.4, 0.7),
        _word("korrekt.", 0.7, 1.2),
    ]
    seg = {"start": 0.0, "end": 1.2, "text": "Das ist korrekt.", "words": words}
    out = reconcile_words_to_text([seg])[0]
    for orig, new in zip(words, out["words"]):
        assert new["start"] == orig["start"] and new["end"] == orig["end"]
        assert new["word"] == orig["word"]


def test_reconcile_heals_language_mixed_desync():
    """Change 160: Desync wie Recording 297 (deutscher Text + fremd-
    sprachige Wörter) wird geheilt: join(words) == text, der Text bleibt
    unantastbar, Matches behalten ihre Zeiten."""
    seg = {
        "start": 350.4,
        "end": 383.83,
        "text": "Ein weiterer Weg führt von der Panzerkaserne raus",
        "words": [
            _word("Мы", 350.405, 351.99),
            _word("сразу", 351.99, 353.58),
            _word("Ein", 353.58, 355.18),
            _word("weiterer", 355.18, 356.77),
        ],
    }
    out = reconcile_words_to_text([seg])[0]
    joined = " ".join(w["word"] for w in out["words"])
    assert joined == seg["text"]
    assert seg["text"] == "Ein weiterer Weg führt von der Panzerkaserne raus"
    # Bei <50% Matches (fremdsprachige Wörter) greift der Gleichverteilungs-
    # Fallback (Change 010) — die Invariante (join==text, gültige Zeiten)
    # zählt, nicht die Match-Zeit-Erhaltung (die gilt erst ab 50% Matches).
    assert all(isinstance(w.get("start"), (int, float)) for w in out["words"])
    assert all(w["end"] > w["start"] for w in out["words"])
