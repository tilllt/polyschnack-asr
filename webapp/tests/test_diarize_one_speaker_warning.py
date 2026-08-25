"""Change 126: _run_diarization warnt, wenn bei langem Audio nur EIN
Speaker erkannt wird.

Live-Befund 2026-08-25: 75-min-Teamtreffen (3 Sprecher) kam mit 26/26
SPEAKER_00 zurück — der diar-Server hatte keinen Embedder (kein globales
Clustering) und alles fiel auf ein Label. Das muss als Warnung sichtbar
werden statt still durchzugehen.
"""
import logging

import pytest

from app import service


def test_run_diarization_warnt_bei_einem_speaker_und_langem_audio(monkeypatch, tmp_path, caplog):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    monkeypatch.setattr(
        "app.diarize.diarize",
        lambda *a, **k: [{"start": 0.0, "end": 2400.0, "speaker": "SPEAKER_00"}],
    )
    with caplog.at_level(logging.WARNING, logger="app.service"):
        service._run_diarization(str(p))
    assert "nur 1 Speaker" in caplog.text
    assert "Embedder" in caplog.text


def test_run_diarization_keine_warnung_bei_mehreren_speakern(monkeypatch, tmp_path, caplog):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    monkeypatch.setattr(
        "app.diarize.diarize",
        lambda *a, **k: [
            {"start": 0.0, "end": 1200.0, "speaker": "SPEAKER_00"},
            {"start": 1200.0, "end": 2400.0, "speaker": "SPEAKER_01"},
        ],
    )
    with caplog.at_level(logging.WARNING, logger="app.service"):
        service._run_diarization(str(p))
    assert "nur 1 Speaker" not in caplog.text


def test_run_diarization_keine_warnung_bei_kurzem_audio(monkeypatch, tmp_path, caplog):
    """Kurze Datei (z. B. 30 s) mit 1 Speaker ist normal — keine Warnung."""
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    monkeypatch.setattr(
        "app.diarize.diarize",
        lambda *a, **k: [{"start": 0.0, "end": 30.0, "speaker": "SPEAKER_00"}],
    )
    with caplog.at_level(logging.WARNING, logger="app.service"):
        service._run_diarization(str(p))
    assert "nur 1 Speaker" not in caplog.text


def test_run_diarization_keine_warnung_bei_leerer_liste(monkeypatch, tmp_path, caplog):
    """Keine Segmente → kein Speaker-Urteil, keine Warnung."""
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    monkeypatch.setattr("app.diarize.diarize", lambda *a, **k: [])
    with caplog.at_level(logging.WARNING, logger="app.service"):
        out = service._run_diarization(str(p))
    assert out == []
    assert "nur 1 Speaker" not in caplog.text
