"""Tests for achetronic-style long-audio chunking (overlap + boundary cascade)."""
from __future__ import annotations

import sys
from pathlib import Path

# Make approach-a importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from polyschnack_service.chunker import (
    ChunkWindow,
    _mel_energy_boundary,
    _midpoint_boundary,
    _vad_boundary,
    chain_boundary,
    plan_chunks,
    plan_chunks_with_boundaries,
)
from polyschnack_service.config import TARGET_SR


# ---------------------------------------------------------------------------
# plan_chunks_with_boundaries — tiling invariant
# ---------------------------------------------------------------------------
def test_single_window_when_audio_fits():
    wins = plan_chunks_with_boundaries(100_000, 300 * TARGET_SR, 15 * TARGET_SR, None, None)
    assert len(wins) == 1
    w = wins[0]
    assert (w.start, w.end, w.emit_start, w.emit_end) == (0, 100_000, 0, 100_000)


def test_tiling_invariant():
    total = 600 * TARGET_SR  # 600 s
    chunk, overlap = 300 * TARGET_SR, 15 * TARGET_SR
    wins = plan_chunks_with_boundaries(total, chunk, overlap, None, None)
    assert len(wins) == 3  # 0-300, 285-585, 570-600 (letzter kürzer)
    for a, b in zip(wins, wins[1:]):
        assert a.emit_end == b.emit_start  # lückenlos
    assert wins[0].emit_start == 0
    assert wins[-1].emit_end == total
    # Overlap existiert (acoustic context)
    assert wins[1].start < wins[0].end


def test_overlap_gives_context():
    total, chunk, overlap = 600 * TARGET_SR, 300 * TARGET_SR, 15 * TARGET_SR
    wins = plan_chunks_with_boundaries(total, chunk, overlap, None, None)
    assert wins[0].start == 0
    assert wins[1].start == (300 - 15) * TARGET_SR  # stride = chunk - overlap


def test_boundary_clamped_into_overlap():
    """Oracle-Ausgabe außerhalb des Overlaps wird in den Overlap geclampt."""
    total, chunk, overlap = 600 * TARGET_SR, 300 * TARGET_SR, 15 * TARGET_SR
    oracle = lambda _w, s, e, m: (0, True)  # viel zu früh
    wins = plan_chunks_with_boundaries(total, chunk, overlap, None, oracle)
    assert wins[0].emit_end >= wins[1].start  # nicht vor Overlap-Start
    assert wins[0].emit_end <= wins[0].end - 1  # nicht über Window-Ende


# ---------------------------------------------------------------------------
# Boundary oracles
# ---------------------------------------------------------------------------
def test_midpoint_always_decides():
    frame, ok = _midpoint_boundary(1000, 2000, 1500)
    assert ok and frame == 1500


def test_mel_energy_prefers_quiet_spot():
    rng = np.random.default_rng(42)
    wav = rng.normal(0, 0.05, 20 * TARGET_SR).astype(np.float32)  # 20 s leise
    wav[5 * TARGET_SR:8 * TARGET_SR] = rng.normal(0, 0.5, 3 * TARGET_SR)  # laut 5-8 s
    frame, ok = _mel_energy_boundary(wav, 4 * TARGET_SR, 10 * TARGET_SR, 7 * TARGET_SR)
    assert ok
    assert 8 * TARGET_SR <= frame <= 10 * TARGET_SR  # leiseste Stelle nach dem lauten Block


def test_mel_energy_small_segment_falls_through():
    frame, ok = _mel_energy_boundary(np.zeros(100, dtype=np.float32), 0, 100, 50)
    assert not ok


def test_vad_boundary_never_crashes():
    # Ohne silero_vad (oder mit) darf die Oracle nie crashen — Fallback = (_, False)
    wav = np.zeros(10 * TARGET_SR, dtype=np.float32)
    frame, ok = _vad_boundary(wav, 0, 10 * TARGET_SR, 5 * TARGET_SR)
    assert isinstance(frame, int) and isinstance(ok, bool)


def test_chain_falls_back_to_midpoint():
    frame, ok = chain_boundary(None, 1000, 2000, 1500)
    assert ok and frame == 1500


def test_chain_uses_mel_when_no_vad():
    rng = np.random.default_rng(7)
    wav = rng.normal(0, 0.05, 20 * TARGET_SR).astype(np.float32)
    wav[5 * TARGET_SR:8 * TARGET_SR] = rng.normal(0, 0.5, 3 * TARGET_SR)
    frame, ok = chain_boundary(wav, 4 * TARGET_SR, 10 * TARGET_SR, 7 * TARGET_SR)
    assert ok
    assert 8 * TARGET_SR <= frame <= 10 * TARGET_SR


# ---------------------------------------------------------------------------
# plan_chunks — public API
# ---------------------------------------------------------------------------
def test_plan_chunks_short_audio_single_window():
    wav = np.zeros(60 * TARGET_SR, dtype=np.float32)
    wins = plan_chunks(wav)
    assert len(wins) == 1
    assert wins[0].emit_start == 0 and wins[0].emit_end == wav.size


def test_plan_chunks_long_audio_tiles():
    wav = np.zeros(600 * TARGET_SR, dtype=np.float32)
    wins = plan_chunks(wav)
    assert len(wins) >= 2
    for a, b in zip(wins, wins[1:]):
        assert a.emit_end == b.emit_start
    assert wins[-1].emit_end == wav.size


# ---------------------------------------------------------------------------
# dedup_seam — seam-level word deduplication (achetronic seam.go)
# ---------------------------------------------------------------------------
from polyschnack_service.core import dedup_seam


def test_dedup_seam_drops_duplicate():
    prev = [{"start": 10.0, "end": 10.3, "word": "to"},
            {"start": 10.3, "end": 10.6, "word": "to"}]
    head = [{"start": 10.45, "end": 10.7, "word": "to"},   # Duplikat
            {"start": 10.9, "end": 11.4, "word": "next"}]
    out = dedup_seam(prev, head)
    assert [w["word"] for w in out] == ["next"]


def test_dedup_seam_keeps_distinct():
    prev = [{"start": 10.0, "end": 10.3, "word": "to"}]
    head = [{"start": 12.0, "end": 12.4, "word": "next"}]
    assert [w["word"] for w in dedup_seam(prev, head)] == ["next"]


def test_dedup_seam_keeps_fast_successor_at_seam():
    """User-Report 2026-08-15: '…gegen' (end 113.64) → 'weiße?' (start 113.7,
    Abstand 0.06 s) wurde verschluckt. In fließender Sprache folgen Wörter
    mit 0.05–0.2 s Abstand — das ist KEIN Duplikat/Kollision, nur eine
    normale Wortgrenze. Nur echte Überlappung verwerfen."""
    prev = [{"start": 113.12, "end": 113.64, "word": "gegen"}]
    head = [{"start": 113.7, "end": 114.05, "word": "weiße?"}]
    out = dedup_seam(prev, head)
    assert [w["word"] for w in out] == ["weiße?"]


def test_dedup_seam_drops_true_overlap_different_text():
    """Anderes Wort an (fast) gleicher Zeit = Kollision → Vorgänger gewinnt."""
    prev = [{"start": 10.0, "end": 11.0, "word": "alt"}]
    head = [{"start": 10.8, "end": 11.5, "word": "neu"}]  # start IM Vorgänger
    assert dedup_seam(prev, head) == []


def test_dedup_seam_empty():
    assert dedup_seam([], [{"start": 1, "end": 2, "word": "x"}])[0]["word"] == "x"
    assert dedup_seam([{"start": 1, "end": 2, "word": "x"}], []) == []


def test_dedup_seam_limits_tail():
    """Nur die letzten SEAM_MAX_WORDS Wörter des Vorgängers zählen."""
    prev = [{"start": float(i), "end": float(i) + 0.3, "word": str(i)} for i in range(10)]
    head = [{"start": 9.1, "end": 9.4, "word": "dup"}]  # kollidiert mit letztem Wort (9.0)
    out = dedup_seam(prev, head)
    assert out == []


# ---------------------------------------------------------------------------
# stitch — emit filtering with ChunkWindows (integration)
# ---------------------------------------------------------------------------
from polyschnack_service.core import stitch


class _FakeResult:
    def __init__(self, text, tokens, timestamps):
        self.text = text
        self.tokens = tokens
        self.timestamps = timestamps


def test_stitch_filters_to_emit_range():
    """Wörter im Overlap-Bereich eines Fensters werden nur einmal emittiert."""
    sr = TARGET_SR
    wins = [
        ChunkWindow(0, 300 * sr, 0, 285 * sr),          # emittiert 0-285 s
        ChunkWindow(285 * sr, 585 * sr, 285 * sr, 570 * sr),  # emittiert 285-570 s
    ]
    # Window 0 transkribiert "world" bei 290 s — das liegt im Overlap und
    # gehört zu Window 1; Window 0 darf es NICHT emittieren (emit_end=285).
    res1 = _FakeResult("hello world",
                       ["▁hello", "▁world"],
                       [0.0, 290.0])
    # Window 1: Timestamps relativ zum Window-Kontext (Start 285 s)
    res2 = _FakeResult("world again",
                       ["▁world", "▁again"],
                       [5.0, 15.0])
    out = stitch(wins, [res1, res2])
    words = [w["word"] for w in out["words"]]
    # "world" (290 s) erscheint genau einmal, aus Window 1; Window 0's Kopie
    # wird vom Emit-Filter verworfen. Kein "world world" an der Naht.
    assert words == ["hello", "world", "again"]
    assert all(w["start"] < 285.0 or w["start"] >= 285.0 for w in out["words"])  # keine Lücke
    starts = [w["start"] for w in out["words"]]
    assert starts == sorted(starts)  # chronologisch


def test_stitch_seam_dedup_across_windows():
    """Duplikate an der Naht (gleiche Zeit) erscheinen nur einmal."""
    sr = TARGET_SR
    wins = [
        ChunkWindow(0, 300 * sr, 0, 285 * sr),
        ChunkWindow(285 * sr, 585 * sr, 285 * sr, 570 * sr),
    ]
    # Beide Fenster transkribieren "next" an derselben Stelle (284.9/285.0 s)
    res1 = _FakeResult("hello next",
                       ["▁hello", "▁next"],
                       [0.0, 284.9])
    # Window 1: Timestamps relativ (next bei 285.0 s absolut = 0.0 relativ)
    res2 = _FakeResult("next again",
                       ["▁next", "▁again"],
                       [0.0, 15.0])
    out = stitch(wins, [res1, res2])
    words = [w["word"] for w in out["words"]]
    assert words.count("next") == 1
    assert "again" in words


# ---------------------------------------------------------------------------
# stitch — Zeit-Offset: Fenster-Kontext (w.start), NICHT emit_start
# ---------------------------------------------------------------------------
def test_stitch_offset_uses_window_start_not_emit_start():
    """Decoder-Timestamps sind relativ zum Fenster-KONTEXT (w.start).

    Vor dem Fix (offset = emit_start) drifteten alle Zeiten eines Fensters
    um (emit_start - start) nach hinten. Beim letzten Fenster wurden die
    letzten echten Wörter über emit_end (= Datei-Ende) hinaus projiziert
    und vom Emit-Filter verworfen — der letzte Satz fehlte. (2026-08-15,
    reproduziert das Produktions-Muster: start=3675, emit=3689.6-3776)
    """
    sr = TARGET_SR
    wins = [
        ChunkWindow(int(3675 * sr), int(3776 * sr),
                    int(3689.6 * sr), int(3776 * sr)),
    ]
    # Decoder liefert "Und wenn sie" relativ zum Fenster-Anfang (3675 s):
    # echt bei 3761.9/3762.1/3762.3 s — knapp vor Datei-Ende (3776).
    res = _FakeResult("Und wenn sie",
                      ["▁Und", "▁wenn", "▁sie"],
                      [86.9, 87.1, 87.3])
    out = stitch(wins, [res])
    starts = [w["start"] for w in out["words"]]
    # Vor dem Fix: offset=3689.6 → 3776.5/3776.7/3776.9 ≥ emit_end (3776)
    # → alle Wörter verworfen. Nach Fix: offset=3675 → 3761.9/3762.1/3762.3.
    assert starts == [3761.9, 3762.1, 3762.3]
    assert [w["word"] for w in out["words"]] == ["Und", "wenn", "sie"]


def test_stitch_multi_window_offsets_are_window_start():
    """Jedes Fenster bekommt seinen w.start als Offset — keine Drift über
    mehrere Fenster, keine Lücken durch weggeworfene Overlap-Wörter."""
    sr = TARGET_SR
    wins = [
        ChunkWindow(0, int(120 * sr), 0, int(114 * sr)),
        ChunkWindow(int(105 * sr), int(225 * sr),
                    int(114 * sr), int(213.6 * sr)),
    ]
    res0 = _FakeResult("A", ["▁A"], [0.0])
    # Window 1: Wort bei relativ 9.0 s → absolut 105 + 9 = 114.0 s
    res1 = _FakeResult("B", ["▁B"], [9.0])
    out = stitch(wins, [res0, res1])
    starts = [w["start"] for w in out["words"]]
    # Vor dem Fix: Window 1 offset=114 → B bei 123.0 s (9 s Drift)
    assert starts == [0.0, 114.0]
    assert [w["word"] for w in out["words"]] == ["A", "B"]


def test_stitch_last_window_keeps_final_words():
    """Der Inhalt des letzten Fensters bis zum Datei-Ende bleibt erhalten
    (Emit-Filter verwirft nur Overlap-Wörter, nie das Fenster-Ende)."""
    sr = TARGET_SR
    wins = [
        ChunkWindow(0, int(300 * sr), 0, int(285 * sr)),
        ChunkWindow(int(285 * sr), int(3776 * sr),
                    int(285 * sr), int(3776 * sr)),
    ]
    res0 = _FakeResult("hello", ["▁hello"], [0.0])
    # Letztes Fenster: Wörter bis ganz ans Ende (relativ 3480.0 = absolut 3765)
    res1 = _FakeResult("goodbye", ["▁goodbye"], [3480.0])
    out = stitch(wins, [res0, res1])
    assert [w["word"] for w in out["words"]] == ["hello", "goodbye"]
    assert out["words"][-1]["start"] == 285.0 + 3480.0
    assert out["words"][-1]["start"] < 3776.0
