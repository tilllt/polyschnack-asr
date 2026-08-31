"""Change 161 (Prävention): Chunk-Overlap-Dopplungen an der ASR-Eingangsstufe.

dedupe_repeated_word_runs entfernt doppelte Wortfolgen, die der ASR-Server
(ps-pk-onnx, 120-s-Chunks) an Chunk-Grenzen doppelt transkribiert — BEVOR
Diarization/Aligner/DB den Text sehen (Live-Befund Recording 8976aa1b:
„Im anliegenden Ort Im anliegenden Ort erzählt man sich…" bei 8:40).
Echte rhetorische Wiederholungen (zeitlich getrennt) bleiben erhalten.
"""
from app.service import dedupe_repeated_word_runs


def _word(w: str, s: float, e: float) -> dict:
    return {"word": w, "start": s, "end": e}


# ---------------------------------------------------------------- Realbefund

def test_dedup_real_chunk_overlap_across_segments():
    """Run 128 (v116): Seg[4] endet „…Im anliegenden", Seg[5] beginnt
    „Ort Im anliegenden Ort erzählt…" — im GLOBALEN Wort-Stream steht die
    volle Phrase „Im anliegenden Ort" zweimal mit überlappenden (Chunk-)
    Zeiten. Die zweite Kopie wird entfernt, Segment-Texte neu gebaut,
    join(words) == text."""
    segs = [
        {
            "start": 467.68,
            "end": 522.0,
            "text": "Die Nebel. Im anliegenden",
            "words": [
                _word("Die", 517.2, 517.6),
                _word("Nebel.", 517.6, 519.36),
                _word("Im", 519.6, 520.16),      # Kopie 1 (Chunk N)
                _word("anliegenden", 520.16, 521.4),
            ],
        },
        {
            "start": 534.16,
            "end": 565.48,
            "text": "Ort Im anliegenden Ort erzählt man sich dass",
            "words": [
                _word("Ort", 521.4, 522.0),          # Kopie 1 Ende (Chunk N)
                _word("Im", 522.0, 522.6),           # Kopie 2 (Chunk N+1, überlappend)
                _word("anliegenden", 522.6, 523.2),
                _word("Ort", 523.2, 523.8),
                _word("erzählt", 533.6, 534.0),      # echte Wörter
                _word("man", 534.0, 534.4),
                _word("sich", 534.4, 534.8),
                _word("dass", 534.8, 535.2),
            ],
        },
    ]
    out, text = dedupe_repeated_word_runs(segs, "Die Nebel. Im anliegenden Ort Im anliegenden Ort erzählt man sich dass")
    joined = " ".join(w["word"] for s in out for w in (s.get("words") or []))
    assert joined == "Die Nebel. Im anliegenden Ort erzählt man sich dass"
    assert text == joined  # Gesamttext konsistent
    # Keine Dopplung mehr im Text
    assert "Ort Im anliegenden Ort" not in text


def test_dedup_real_phrase_inside_single_segment():
    """Dopplung INNERHALB eines Segments: „Im anliegenden Ort Im anliegenden
    Ort erzählt…" mit überlappenden Chunk-Zeiten → zweite Kopie weg."""
    segs = [{
        "start": 519.6,
        "end": 536.1,
        "text": "Im anliegenden Ort Im anliegenden Ort erzählt man sich",
        "words": [
            _word("Im", 519.6, 520.16),
            _word("anliegenden", 520.16, 521.4),
            _word("Ort", 521.4, 522.0),
            _word("Im", 522.0, 522.6),        # Chunk-Overlap-Kopie
            _word("anliegenden", 522.6, 523.8),
            _word("Ort", 523.8, 524.4),
            _word("erzählt", 533.6, 534.0),   # echte Wörter
            _word("man", 534.0, 534.4),
            _word("sich", 534.4, 534.8),
        ],
    }]
    out, text = dedupe_repeated_word_runs(segs, segs[0]["text"])
    joined = " ".join(w["word"] for w in out[0]["words"])
    assert joined == "Im anliegenden Ort erzählt man sich"
    assert out[0]["text"] == joined
    assert text == joined


# ------------------------------------------------------ Echte Wiederholungen

def test_dedup_keeps_real_hesitation_repetition():
    """Rhetorische/zeitlich getrennte Wiederholung („Im anliegenden Ort …“
    später nochmal) — KEIN Chunk-Overlap: start2 deutlich NACH end1 →
    bleibt vollständig erhalten."""
    segs = [{
        "start": 0.0,
        "end": 30.0,
        "text": "Im anliegenden Ort ist schön Im anliegenden Ort gefällt mir",
        "words": [
            _word("Im", 0.0, 0.5), _word("anliegenden", 0.5, 1.0), _word("Ort", 1.0, 1.5),
            _word("ist", 1.5, 2.0), _word("schön", 2.0, 2.5),
            _word("Im", 15.0, 15.5), _word("anliegenden", 15.5, 16.0), _word("Ort", 16.0, 16.5),
            _word("gefällt", 16.5, 17.0), _word("mir", 17.0, 17.5),
        ],
    }]
    out, text = dedupe_repeated_word_runs(segs, segs[0]["text"])
    assert len(out[0]["words"]) == 10  # nichts entfernt
    assert out[0]["text"] == segs[0]["text"]


def test_dedup_keeps_short_ja_ja_without_ts():
    """Ohne Wort-Zeiten greift erst ab n >= 3 — „ja ja“ (n=2) bleibt."""
    segs = [{"start": 0.0, "end": 2.0, "text": "ja ja das ist gut"}]
    out, text = dedupe_repeated_word_runs(segs, segs[0]["text"])
    assert out[0]["text"] == "ja ja das ist gut"


# ------------------------------------------------------------- Fallback/Edge

def test_dedup_fallback_without_timestamps():
    """Text ohne Wort-Zeiten (Fallback): identische benachbarte Folge
    n >= 3 wird entfernt, auch segmentübergreifend."""
    segs = [
        {"start": 0.0, "end": 5.0, "text": "Im anliegenden Ort Im anliegenden"},
        {"start": 5.0, "end": 10.0, "text": "Ort erzählt man sich"},
    ]
    out, text = dedupe_repeated_word_runs(segs, "Im anliegenden Ort Im anliegenden Ort erzählt man sich")
    joined = " ".join((s.get("text") or "").strip() for s in out).strip()
    assert joined == "Im anliegenden Ort erzählt man sich"
    assert text == joined


def test_dedup_consistent_segments_untouched():
    """Konsistente Segmente ohne Dopplung → exakt 1:1 (Objekte unverändert)."""
    segs = [
        {"start": 0.0, "end": 2.0, "text": "Guten Tag", "words": [_word("Guten", 0.0, 1.0), _word("Tag", 1.0, 2.0)]},
        {"start": 2.0, "end": 4.0, "text": "hier ist Till", "words": [_word("hier", 2.0, 2.5), _word("ist", 2.5, 3.0), _word("Till", 3.0, 4.0)]},
    ]
    out, text = dedupe_repeated_word_runs(segs, "Guten Tag hier ist Till")
    assert out == segs
    assert text == "Guten Tag hier ist Till"


def test_dedup_short_stream_noop():
    """Zu kurzer Stream (< 2*min_run) → unverändert."""
    segs = [{"start": 0.0, "end": 1.0, "text": "nur ein Wort"}]
    out, text = dedupe_repeated_word_runs(segs, "nur ein Wort")
    assert out == segs
    assert text == "nur ein Wort"


def test_dedup_removes_only_second_copy_keeps_first():
    """Erste Kopie (echte akustische Position) bleibt, zweite (Overlap) fällt."""
    segs = [{
        "start": 0.0,
        "end": 6.0,
        "text": "a b c a b c d",
        "words": [
            _word("a", 0.0, 0.4), _word("b", 0.4, 0.8), _word("c", 0.8, 1.2),   # erste Kopie
            _word("a", 1.2, 1.6), _word("b", 1.6, 2.0), _word("c", 2.0, 2.4),   # Overlap-Kopie
            _word("d", 2.4, 2.8),
        ],
    }]
    out, _ = dedupe_repeated_word_runs(segs, segs[0]["text"])
    joined = " ".join(w["word"] for w in out[0]["words"])
    assert joined == "a b c d"


# ----------------------------------------------------- Change 167: Dauer-Signatur

def test_dedup_real_297_stretched_first_copy_with_gap():
    """ECHTER Fall 297 (Ergebnis 130 / Run 140, 2026-08-31, DB-Wort-Zeiten):
    Kopie 1 liegt in der Stille („anliegenden" 6,0 s, „Ort" 3,27 s), Kopie 2
    (echt, ab 533,64) beginnt 4,2 s nach Kopie-1-Ende → Zeit-Overlap-Signatur
    verfehlt (533,64 > 529,43 + 1,0). Die Dauer-Signatur (Change 167) muss
    die gestreckte Kopie 1 entfernen."""
    segs = [
        {
            "start": 467.68,
            "end": 522.0,
            "text": "Die Nebel. Im anliegenden",
            "words": [
                _word("Die", 517.2, 517.6),
                _word("Nebel.", 517.6, 519.36),
                _word("Im", 519.6, 520.16),       # Kopie 1: normal
                _word("anliegenden", 520.16, 526.16),  # 6,0 s — Stille!
            ],
        },
        {
            "start": 534.16,
            "end": 565.48,
            "text": "Ort Im anliegenden Ort erzählt man sich dass",
            "words": [
                _word("Ort", 526.16, 529.43),     # 3,27 s — Stille!
                _word("Im", 533.64, 534.44),      # Kopie 2: echte Zeiten
                _word("anliegenden", 534.44, 534.84),
                _word("Ort", 534.84, 535.64),
                _word("erzählt", 535.64, 536.12),
                _word("man", 536.12, 536.84),
                _word("sich", 536.84, 537.56),
                _word("dass", 537.56, 537.88),
            ],
        },
    ]
    out, text = dedupe_repeated_word_runs(
        segs, "Die Nebel. Im anliegenden Ort Im anliegenden Ort erzählt man sich dass")
    joined = " ".join(w["word"] for s in out for w in (s.get("words") or []))
    assert joined == "Die Nebel. Im anliegenden Ort erzählt man sich dass"
    assert text == joined
    assert "Ort Im anliegenden Ort" not in text


def test_dedup_stretched_second_copy_symmetric():
    """Symmetrie: Die gestreckte (Stille-)Kopie ist die ZWEITE → sie fällt,
    die erste (echte) bleibt. Lücke > 1 s, damit die Zeit-Signatur nicht greift."""
    segs = [{
        "start": 0.0,
        "end": 8.0,
        "text": "a b c a b c d",
        "words": [
            _word("a", 0.0, 0.4), _word("b", 0.4, 0.8), _word("c", 0.8, 1.2),   # echt
            _word("a", 3.0, 3.5), _word("b", 3.5, 6.5), _word("c", 6.5, 7.0),   # b=3,0 s — Stille!
            _word("d", 7.0, 7.4),
        ],
    }]
    out, _ = dedupe_repeated_word_runs(segs, segs[0]["text"])
    joined = " ".join(w["word"] for w in out[0]["words"])
    assert joined == "a b c d"
