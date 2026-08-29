"""Tests für den Forced-Aligner-Client + Alignment-Phase (Karaoke-Word-Sync).

Die Integrationstests starten den echten aligner_server.py-Wrapper als
Subprocess mit einer Fake-qwen3-asr-cli — echter HTTP-Roundtrip ohne Docker.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import httpx

from app.aligner_client import AlignerClient
from app.service import (
    MAX_ALIGN_GROUP_S,
    _run_align_phase,
    apply_aligned_words,
    build_align_groups,
)

REPO = Path(__file__).resolve().parents[2]  # webapp/tests/ → Repo-Root (pk-asr)
WRAPPER = REPO / "app" / "aligner_client.py"  # nicht genutzt — nur Guard


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def aligner_server():
    """Startet den Wrapper (mit Fake-CLI) auf einem freien Port."""
    fake_cli = REPO / "aligner-service" / "tests" / "fake_cli.sh"
    model = REPO / "aligner-service" / "tests" / "fake_model.gguf"
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "aligner-service" / "aligner_server.py"),
         "--cli", str(fake_cli), "--model", str(model), "--port", str(port),
         # Change 133: alle 4 Modell-Pfade müssen existieren (Startprüfung)
         "--model-tada", str(model),
         "--model-tada-codec", str(model),
         "--model-wav2vec2", str(model)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Wrapper nicht gestartet")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture()
def wav_bytes() -> bytes:
    # 1 s Sine-Wave → 16k mono WAV (32 kB)
    out = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-ar", "16000", "-ac", "1", "-f", "wav", "-"],
        capture_output=True, check=True,
    )
    return out.stdout


# ============================================================
# AlignerClient — echter HTTP-Roundtrip gegen den Wrapper
# ============================================================

def test_align_roundtrip(aligner_server, wav_bytes):
    c = AlignerClient(url=aligner_server, timeout=30)
    assert c.health() is True
    words = c.align(wav_bytes, "Hallo Welt", lang="de")
    assert len(words) == 2
    assert words[0]["word"] == "Hallo"
    assert words[0]["start"] == 0.0


def test_align_missing_text_422(aligner_server, wav_bytes):
    c = AlignerClient(url=aligner_server, timeout=30)
    with pytest.raises(RuntimeError) as ei:
        c.align(wav_bytes, "", lang="de")
    assert "422" in str(ei.value)


def test_align_client_unreachable():
    c = AlignerClient(url="http://127.0.0.1:1", timeout=5)
    assert c.health() is False
    with pytest.raises(RuntimeError):
        c.align(b"x", "Hallo")


# ============================================================
# build_align_groups / apply_aligned_words (pure Logik)
# ============================================================

def test_build_align_groups_buendelt_unter_limit():
    segs = [
        {"start": 0, "end": 100, "text": "A"},
        {"start": 100, "end": 200, "text": "B"},
        {"start": 200, "end": 300, "text": "C"},
        {"start": 300, "end": 400, "text": "D"},
    ]
    groups = build_align_groups(segs, max_s=380.0)
    assert len(groups) == 2  # 0-300 (300s) + 300-400 — Span 400 > 380
    assert groups[0] == (0, 300, "A B C")
    assert groups[1] == (300, 400, "D")


def test_build_align_groups_einzelnes_langes_segment_wird_gechunkt():
    """Change 078: Ein Segment LÄNGER als max_s wird intern in Chunks
    geteilt (User-Vorgabe: GUI-Segmente ≠ Align-Chunks) — der Aligner
    bekommt technisch optimierte Stücke, die Wörter werden danach über
    apply_aligned_words wieder dem Original-Segment zugeordnet."""
    segs = [{"start": 0, "end": 500, "text": "eins zwei drei vier fünf"}]
    groups = build_align_groups(segs, max_s=380.0)
    assert len(groups) == 2  # 500 s → ceil(500/380) = 2 Chunks
    # Chunk 1: 0–250, Chunk 2: 250–500 (je ≤ max_s)
    assert groups[0][0] == 0.0
    assert groups[1][1] == 500.0
    # Texte decken den Gesamttext verlustfrei ab (Reihenfolge!)
    joined = " ".join(g[2] for g in groups)
    assert joined == "eins zwei drei vier fünf"


def test_apply_aligned_words_ableitet_dauer_aus_folgewort():
    """Change 152: Wörter mit end=start (Dauer 0) bekommen die Dauer aus
    dem Start des Folgeworts — aber NIE über eine Stille-Lücke (> 0.5 s)
    hinweg (Satz-Ende); das letzte Wort bekommt die typische Dauer."""
    segs = [{"start": 0.0, "end": 6.0, "text": "eins zwei drei vier"}]
    words = [
        {"word": "eins", "start": 0.10, "end": 0.10},   # Dauer 0
        {"word": "zwei", "start": 0.40, "end": 0.40},   # Dauer 0
        {"word": "drei", "start": 0.70, "end": 0.70},   # Dauer 0
        {"word": "vier", "start": 5.00, "end": 5.00},   # nach langer Stille
    ]
    out = apply_aligned_words(segs, words, group_start=0.0)
    ws = out[0]["words"]
    assert ws[0]["end"] == pytest.approx(0.40)      # kleine Lücke → Folgewort
    assert ws[1]["end"] == pytest.approx(0.70)
    cap = 1.0  # harte Maximaldauer (User 2026-08-28)
    assert ws[2]["end"] == pytest.approx(0.70 + cap)  # Stille NICHT übernommen
    assert ws[3]["end"] == pytest.approx(5.00 + cap)  # letztes Wort: Cap
    assert ws[3]["end"] > ws[3]["start"]


def test_apply_aligned_words_behaelt_echte_dauer():
    """Change 152: Wörter mit plausibler Dauer (> 50 ms) bleiben unberührt."""
    segs = [{"start": 0.0, "end": 3.0, "text": "eins zwei"}]
    words = [
        {"word": "eins", "start": 0.10, "end": 0.40},
        {"word": "zwei", "start": 0.50, "end": 0.90},
    ]
    out = apply_aligned_words(segs, words, group_start=0.0)
    ws = out[0]["words"]
    assert ws[0]["end"] == pytest.approx(0.40)
    assert ws[1]["end"] == pytest.approx(0.90)


def test_build_align_groups_mehrere_chunks_unter_max():
    """Change 078: 500-s-Segment mit max_s=120 → 5 Chunks, jeder ≤ 120 s."""
    segs = [{"start": 0, "end": 500, "text": " ".join(f"w{i}" for i in range(10))}]
    groups = build_align_groups(segs, max_s=120.0)
    assert len(groups) == 5
    for gs, ge, _txt in groups:
        assert ge - gs <= 120.0 + 1e-6
    joined = " ".join(g[2] for g in groups)
    assert joined == " ".join(f"w{i}" for i in range(10))


def test_build_align_groups_leere_segmente():
    assert build_align_groups([]) == []
    assert build_align_groups([{"text": "noch ohne zeit"}]) == []


def test_apply_aligned_words_offset_und_zuordnung():
    segs = [
        {"start": 10, "end": 20, "text": "erste zweite"},
        {"start": 20, "end": 30, "text": "dritte"},
    ]
    words = [
        {"start": 1.0, "end": 1.5, "word": "erste"},
        {"start": 1.6, "end": 2.0, "word": "zweite"},
        {"start": 12.0, "end": 12.5, "word": "dritte"},  # global 22.0 → Segment 2
    ]
    out = apply_aligned_words(segs, words, group_start=10.0)
    assert out[0]["words"][0] == {"word": "erste", "start": 11.0, "end": 11.5}
    assert out[0]["words"][1]["start"] == 11.6
    assert out[0]["words"][1]["end"] == 12.0
    assert out[1]["words"][0] == {"word": "dritte", "start": 22.0, "end": 22.5}
    # Ursprungs-Segmente unangetastet (Kopie)
    assert segs[0].get("words") is None


def test_apply_aligned_words_mehrere_chunks_zu_einem_segment():
    """Change 078: Wörter aus MEHREREN Align-Chunks (global, Offset 0)
    landen ALLE im Segment — die alte Pro-Gruppe-Anwendung hätte sie mit
    der letzten Gruppe überschrieben."""
    segs = [{"start": 0, "end": 500, "text": "eins zwei drei"}]
    words = [
        {"start": 1.0, "end": 1.5, "word": "eins"},    # Chunk 1 (0–250)
        {"start": 250.0, "end": 250.5, "word": "zwei"},  # Chunk 2 (250–500)
        {"start": 300.0, "end": 300.5, "word": "drei"},
    ]
    out = apply_aligned_words(segs, words, group_start=0.0)
    assert len(out[0]["words"]) == 3
    assert [w["word"] for w in out[0]["words"]] == ["eins", "zwei", "drei"]


# ============================================================
# _run_align_phase — Integration gegen den lokalen Wrapper
# (db-Prozesse werden gemockt; die Phase selbst ist der Fokus)
# ============================================================

def test_run_align_phase_ersetzt_words(aligner_server, wav_bytes, monkeypatch):
    from app import service as svc

    monkeypatch.setattr(svc, "engine", None)  # keine DB — Phase nutzt Sessions nur für Progress
    # Session/engine-Nutzung abfangen: set_progress & Recording-Handling mocken
    calls = {"set_progress": [], "rec_get": []}

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, model, rid):
            calls["rec_get"].append(rid)
            return None  # rec2 None → keine commits
    monkeypatch.setattr(svc, "Session", lambda engine: _FakeSession())
    monkeypatch.setattr(svc, "set_progress", lambda s, rid, pct, note=None: calls["set_progress"].append((rid, pct, note)))
    monkeypatch.setattr(svc, "engine", object())  # Session(engine) nutzt den Wert nur als Arg

    # AlignerClient auf den lokalen Wrapper zeigen
    from app import aligner_client as ac
    monkeypatch.setattr(ac, "ALIGN_URL", aligner_server)

    segs = [{"start": 0, "end": 1, "text": "Hallo Welt"}]
    out = _run_align_phase(7, segs, wav_bytes, "a.wav", "de")
    assert out[0]["words"] == [
        {"word": "Hallo", "start": 0.0, "end": 0.4},
        {"word": "Welt", "start": 0.4, "end": 0.9},
    ]
    # Change 151: Progress-Hinweis kam — phasen-lokal: Start 0 mit
    # note="alignment" (der Gruppen-Balken 0..100 hängt an der
    # Gruppen-Bildung und ist hier nicht deterministisch).
    assert any(
        c[0] == 7 and c[1] == 0 and str(c[2]) == "alignment"
        for c in calls["set_progress"]
    )
    assert any(
        c[0] == 7 and str(c[2]).startswith("alignment")
        for c in calls["set_progress"]
    )


def test_run_align_phase_skip_wenn_down(monkeypatch):
    from app import service as svc
    from app import aligner_client as ac

    monkeypatch.setattr(ac, "ALIGN_URL", "http://127.0.0.1:1")  # sicher down
    monkeypatch.setattr(svc, "engine", object())
    monkeypatch.setattr(svc, "Session", lambda engine: None)
    monkeypatch.setattr(svc, "set_progress", lambda s, rid, pct, note=None: None)

    segs = [{"start": 0, "end": 1, "text": "Hallo"}]
    out = _run_align_phase(7, segs, b"x", "a.wav", "de")
    assert out == segs  # unverändert


# ============================================================
# Change 045 — Hintergrund-Alignment (_run_background_align)
# ============================================================

class _FakeRecording:
    """Minimales Recording-Objekt für den Worker-Test (attributbasiert)."""

    def __init__(self, segments, status="done", alignment="pending"):
        self.id = 7
        self.status = status
        self.segments = list(segments)
        self.language = "de"
        self.alignment = alignment
        self.error = None
        self.commits = 0

    def __repr__(self):
        return f"<FakeRecording alignment={self.alignment}>"


class _FakeSession:
    def __init__(self, rec):
        self.rec = rec

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, model, rid):
        return self.rec

    def add(self, obj):
        pass

    def commit(self):
        if self.rec is not None:
            self.rec.commits += 1


def test_alignment_cache_roundtrip(tmp_path, monkeypatch):
    from app.service import _AlignmentCache

    monkeypatch.setattr(_AlignmentCache, "_DIR", tmp_path / "cache")
    # Neues Format (Change 114): vad_meta-dict
    _AlignmentCache.write(7, b"audio-bytes",
                          vad_meta={"type": "shift", "offset_s": 1.5})
    assert _AlignmentCache.read(7) == b"audio-bytes"
    assert _AlignmentCache.read_vad_meta(7) == {"type": "shift", "offset_s": 1.5}
    _AlignmentCache.delete(7)
    assert _AlignmentCache.read(7) is None
    assert _AlignmentCache.read_vad_meta(7) is None
    assert _AlignmentCache.read_meta(7) == 0.0

    # Alt-Format (float trim_offset_s) bleibt kompatibel lesbar
    _AlignmentCache.write(8, b"alt", 1.5)
    assert _AlignmentCache.read_vad_meta(8) == {"type": "shift", "offset_s": 1.5}
    assert _AlignmentCache.read_meta(8) == 1.5


def test_background_align_cache_fehlt_skipped(tmp_path, monkeypatch):
    from app import service as svc

    # Change 155 (Schritt 4): Audio wird selbst vorbereitet — fehlt es
    # (Datei weg/nicht lesbar), → skipped (kein stiller Erfolg).
    monkeypatch.setattr(svc, "engine", object())
    rec = _FakeRecording([], alignment="pending")
    monkeypatch.setattr(svc, "Session", lambda engine: _FakeSession(rec))
    monkeypatch.setattr(svc, "_prepare_align_audio", lambda *a, **k: None)

    svc._run_background_align(7)
    assert rec.alignment == "skipped"


def test_background_align_ersetzt_words(aligner_server, wav_bytes, tmp_path, monkeypatch):
    """Worker: Audio vorbereitet → Aligner → Segmente aktualisiert, alignment=done."""
    from app import service as svc
    from app import aligner_client as ac

    monkeypatch.setattr(ac, "ALIGN_URL", aligner_server)
    monkeypatch.setattr(svc, "engine", object())

    rec = _FakeRecording([{"start": 0, "end": 1, "text": "Hallo Welt"}])
    monkeypatch.setattr(svc, "Session", lambda engine: _FakeSession(rec))

    # Audio wie der Queue-Fluss vorbereitet (verarbeitete Bytes, kein Trim).
    monkeypatch.setattr(svc, "_prepare_align_audio", lambda *a, **k: (wav_bytes, None))

    svc._run_background_align(7)
    assert rec.alignment == "done"
    words = rec.segments[0].get("words") or []
    assert [w["word"] for w in words] == ["Hallo", "Welt"]


def test_background_align_versionsguard_verwirft(tmp_path, monkeypatch):
    """Worker: Segmente während des Laufs geändert → Ergebnis verworfen."""
    from app import service as svc

    monkeypatch.setattr(svc, "engine", object())

    # Geteilter Zähler über alle Session-Instanzen (Session() wird pro
    # with-Block neu erzeugt — der Zähler darf nicht pro Instanz starten).
    counter = {"reads": 0}

    class _MutableFakeSession(_FakeSession):
        """get() mutiert die Segmente beim 2. Read (simuliert User-Edit)."""

        def get(self, model, rid):
            counter["reads"] += 1
            if counter["reads"] >= 2:
                # User-Edit zwischen Baseline-Read und Write-Check
                self.rec.segments = [{"start": 0, "end": 1, "text": "User-Korrektur"}]
            return self.rec

    # Aligner down → _run_align_phase gibt segments unverändert zurück,
    # aber der Guard vergleicht trotzdem: Baseline != aktuell → skipped.
    from app import aligner_client as ac

    monkeypatch.setattr(ac, "ALIGN_URL", "http://127.0.0.1:1")

    rec = _FakeRecording([{"start": 0, "end": 1, "text": "Hallo Welt"}])
    monkeypatch.setattr(svc, "Session", lambda engine: _MutableFakeSession(rec))
    monkeypatch.setattr(svc, "_prepare_align_audio", lambda *a, **k: (b"x", None))

    svc._run_background_align(7)
    assert rec.alignment == "skipped"


def test_background_align_ohne_effekt_ist_skipped_nicht_done(tmp_path, monkeypatch):
    """Change 101: Aligner down → Wörter unverändert → NIE „done“ — skipped
    mit Grund. Vorher: alignment=done trotz identischer Wörter (stille Lüge;
    User-Befund „Re-Align bringt nichts“, Karaoke rast im 80-ms-Raster)."""
    from app import service as svc
    from app import aligner_client as ac

    monkeypatch.setattr(ac, "ALIGN_URL", "http://127.0.0.1:1")  # sicher down
    monkeypatch.setattr(svc, "engine", object())

    rec = _FakeRecording([{
        "start": 0, "end": 1, "text": "Hallo Welt",
        "words": [{"word": "Hallo", "start": 0.0, "end": 0.5}],
    }])
    monkeypatch.setattr(svc, "Session", lambda engine: _FakeSession(rec))
    monkeypatch.setattr(svc, "_prepare_align_audio", lambda *a, **k: (b"x", None))

    svc._run_background_align(7)
    assert rec.alignment == "skipped"
    assert "Aligner nicht erreichbar" in (rec.error or "")
    # Die (unveränderten) Wörter blieben erhalten
    assert rec.segments[0]["words"][0]["word"] == "Hallo"


def test_background_align_leere_woerter_skipped_mit_grund(tmp_path, monkeypatch):
    """Change 101: Aligner erreichbar, liefert aber keine Wörter → skipped
    mit passendem Grund (nicht „done“)."""
    from app import service as svc
    from app import aligner_client as ac

    class _FakeClient:
        def health(self):
            return True

        def align(self, audio, text, lang="de", timeout_s=None):
            return []

    monkeypatch.setattr(ac, "AlignerClient", _FakeClient)
    monkeypatch.setattr(svc, "engine", object())

    rec = _FakeRecording([{"start": 0, "end": 1, "text": "Hallo Welt"}])
    monkeypatch.setattr(svc, "Session", lambda engine: _FakeSession(rec))
    monkeypatch.setattr(svc, "_prepare_align_audio", lambda *a, **k: (b"x", None))

    svc._run_background_align(7)
    assert rec.alignment == "skipped"
    assert "keine Wort-Timestamps" in (rec.error or "")


# ============================================================
# Change 133: method-Dispatch (qwen3/tada/wav2vec2)
# ============================================================

def test_aligner_args_qwen3_default():
    """Default-Methode qwen3 -> CrispASR --align-only -am <qwen3-FA>."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "aligner_server", REPO / "aligner-service" / "aligner_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    models = {"qwen3": "/m/qwen3.gguf", "tada": "/m/tada.gguf",
              "tada_codec": "/m/codec.gguf", "wav2vec2": "/m/w2v.gguf"}
    args = mod._aligner_args("qwen3", models, "/tmp/a.wav", "Hallo Welt", "de", "/tmp/o.json")
    assert args[0] == "--align-only"
    assert args[1] == "-am"
    assert "/m/qwen3.gguf" in args
    assert "--ref-text" in args
    assert "Hallo Welt" in args
    assert args[-1] == "/tmp/o.json"


def test_aligner_args_tada():
    """TADA -> -m <tada> --codec-model <codec> --align --voice ... --source-lang."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "aligner_server", REPO / "aligner-service" / "aligner_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    models = {"qwen3": "/m/qwen3.gguf", "tada": "/m/tada.gguf",
              "tada_codec": "/m/codec.gguf", "wav2vec2": "/m/w2v.gguf"}
    args = mod._aligner_args("tada", models, "/tmp/a.wav", "Hallo", "de", "/tmp/o.json")
    joined = " ".join(args)
    assert args[0] == "-m"
    assert "/m/tada.gguf" in args
    assert "--codec-model" in args and "/m/codec.gguf" in args
    assert "--align" in args
    assert "--voice" in args and "/tmp/a.wav" in args
    assert "--source-lang" in args and "de" in args
    assert "--align-output" in joined


def test_aligner_args_wav2vec2():
    """wav2vec2 -> --align-only -am <wav2vec2-xlsr-de>."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "aligner_server", REPO / "aligner-service" / "aligner_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    models = {"qwen3": "/m/qwen3.gguf", "tada": "/m/tada.gguf",
              "tada_codec": "/m/codec.gguf", "wav2vec2": "/m/w2v.gguf"}
    args = mod._aligner_args("wav2vec2", models, "/tmp/a.wav", "Hallo", "de", "/tmp/o.json")
    assert args[0] == "--align-only"
    assert "/m/w2v.gguf" in args
    assert "--ref-text" in args


def test_aligner_args_unbekannte_methode_raises():
    """Unbekannte Methode -> ValueError (Server antwortet 422)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "aligner_server", REPO / "aligner-service" / "aligner_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    models = {"qwen3": "/m/qwen3.gguf", "tada": "/m/tada.gguf",
              "tada_codec": "/m/codec.gguf", "wav2vec2": "/m/w2v.gguf"}
    with pytest.raises(ValueError):
        mod._aligner_args("xyz", models, "/tmp/a.wav", "Hallo", "de", "/tmp/o.json")


def test_align_method_roundtrip(aligner_server, wav_bytes):
    """method-Feld wird an den Service durchgereicht (Default qwen3 ok)."""
    c = AlignerClient(url=aligner_server, timeout=30)
    words = c.align(wav_bytes, "Hallo Welt", lang="de", method="tada")
    assert len(words) == 2
    assert words[0]["word"] == "Hallo"


def test_align_method_unbekannt_422(aligner_server, wav_bytes):
    """Unbekannte Methode -> 422 vom Service."""
    c = AlignerClient(url=aligner_server, timeout=30)
    with pytest.raises(RuntimeError) as ei:
        c.align(wav_bytes, "Hallo Welt", lang="de", method="nope")
    assert "422" in str(ei.value)
