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
         "--cli", str(fake_cli), "--model", str(model), "--port", str(port)],
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


def test_build_align_groups_einzelnes_langes_segment():
    segs = [{"start": 0, "end": 500, "text": "Lang"}]
    groups = build_align_groups(segs, max_s=380.0)
    assert len(groups) == 1  # einzelnes Segment bleibt eigene Gruppe
    assert groups[0] == (0, 500, "Lang")


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
    # Progress-Hinweis kam: 96 mit note=alignment
    assert (7, 96, "alignment") in calls["set_progress"]


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
