"""Merge-Upload: POST /recordings/merge fügt mehrere Aufnahmen in der
angegebenen Reihenfolge zu EINER Datei zusammen (ffmpeg concat) und löscht
die Einzeldateien (Row + Datei)."""

from __future__ import annotations

import shutil
import struct
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg nicht verfügbar"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'merge.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


from fastapi.testclient import TestClient  # noqa: E402


def _make_wav(path: Path, seconds: float = 1.0, freq: int = 440) -> bytes:
    """1-sekündige 8-kHz-mono-WAV (klein, ffmpeg-konform)."""
    import math

    rate = 8000
    n = int(rate * seconds)
    samples = []
    for i in range(n):
        v = int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / rate))
        samples.append(struct.pack("<h", v))
    buf = b"".join(samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(buf)
    return buf


def _upload(client, name: str, path: Path) -> dict:
    resp = client.post(
        "/api/recordings",
        files={"file": (name, path.read_bytes(), "audio/wav")},
        data={"batch_id": "batch-merge"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_merge_zwei_dateien_eine_aufnahme(client, tmp_path):
    f1 = tmp_path / "a.wav"
    f2 = tmp_path / "b.wav"
    _make_wav(f1, 1.0, 440)
    _make_wav(f2, 1.0, 880)

    r1 = _upload(client, "a.wav", f1)
    r2 = _upload(client, "b.wav", f2)

    resp = client.post(
        "/api/recordings/merge",
        json={"uids": [r1["uid"], r2["uid"]], "batch_id": "batch-merge"},
    )
    assert resp.status_code == 201, resp.text
    merged = resp.json()

    assert merged["original_name"].startswith("Merge (2 Dateien)")
    assert merged["mime"] == "audio/wav"
    # Dauer = Summe der Einzeldateien (~2 s)
    assert merged["duration_s"] is not None and merged["duration_s"] >= 1.9

    # Einzelaufnahmen + Dateien sind weg
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        assert s.get(Recording, r1["id"]) is None
        assert s.get(Recording, r2["id"]) is None
        merged_row = s.get(Recording, merged["id"])
        assert merged_row is not None
        assert Path(merged_row.stored_path).is_file()

    # Merge-Datei ist länger als jede Einzeldatei (rekursiv — Change 014:
    # anon-Merge liegt in AUDIO_DIR/anon/).
    from app.config import settings

    files = list(Path(settings.AUDIO_DIR).rglob("*.wav"))
    assert len(files) == 1  # nur die Merge-Datei übrig


def test_merge_braucht_min_2_dateien(client, tmp_path):
    f1 = tmp_path / "a.wav"
    _make_wav(f1, 1.0, 440)
    r1 = _upload(client, "a.wav", f1)
    resp = client.post("/api/recordings/merge", json={"uids": [r1["uid"]]})
    assert resp.status_code == 400


def test_merge_unbekannte_uid_404(client, tmp_path):
    f1 = tmp_path / "a.wav"
    _make_wav(f1, 1.0, 440)
    r1 = _upload(client, "a.wav", f1)
    resp = client.post(
        "/api/recordings/merge",
        json={"uids": [r1["uid"], "doesnotexist"]},
    )
    assert resp.status_code == 404
