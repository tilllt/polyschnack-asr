"""Test: Upload einer SEHR KURZEN Aufnahme (User-Befund 2026-08-21:
mobile Aufnahme → 'recording saved locally upload pending', Retry → 500)."""
from __future__ import annotations

import io
import os
import tempfile
import wave
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="short_upload_test_")
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("BENCHMARK_API_KEYS", "test-key-123")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from app import db as db_module
    from app.main import app
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    with TestClient(app) as c:
        yield c


def _wav_bytes(duration_s: float, sample_rate: int = 16000) -> bytes:
    """Kleine echte WAV-Datei (Stille) mit exakter Dauer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        n = int(duration_s * sample_rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def test_upload_very_short_wav(client):
    """0,1 s WAV → 201 (nicht 500)."""
    r = client.post(
        "/api/recordings",
        files={"file": ("kurz.wav", _wav_bytes(0.1), "audio/wav")},
    )
    assert r.status_code == 201, r.text


def test_upload_10ms_wav(client):
    """0,01 s WAV → 201 (nicht 500)."""
    r = client.post(
        "/api/recordings",
        files={"file": ("mini.wav", _wav_bytes(0.01), "audio/wav")},
    )
    assert r.status_code == 201, r.text


def test_upload_empty_wav_header_only(client):
    """Nur WAV-Header (0 Frames) — die Datei existiert, hat aber keinen
    Ton: darf 201 liefern oder einen sauberen 4xx, nie 500."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"")
    r = client.post(
        "/api/recordings",
        files={"file": ("leer.wav", buf.getvalue(), "audio/wav")},
    )
    assert r.status_code in (201, 400, 422), r.text


def test_upload_tiny_garbage(client):
    """12 Bytes Müll (kaputter Recorder-Blob) → sauberes 422 mit Meldung
    (Befund 2026-08-21: war RuntimeError → 500; jetzt verständlich)."""
    r = client.post(
        "/api/recordings",
        files={"file": ("kaputt.bin", b"\x00" * 12, "application/octet-stream")},
    )
    assert r.status_code == 422, r.text
    assert "Audio konnte nicht gelesen werden" in r.json()["detail"]
