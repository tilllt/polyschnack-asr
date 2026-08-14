"""Duplikat-Upload: POST /recordings/{rid}/duplicate legt eine neue Aufnahme
aus der vorhandenen Datei an — kein Re-Upload übers Netz (bei 300+-MB-Dateien
blieb der „Upload again"-Dialog sonst minutenlang bei 100%), Peaks werden
vom Original übernommen (identischer Inhalt → identische Wellenform)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'dup.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _upload(client) -> dict:
    resp = client.post(
        "/api/recordings",
        files={"file": ("zoom.mp3", b"fake-audio-bytes", "audio/mpeg")},
        data={"batch_id": "b1"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_duplicate_legt_neue_aufnahme_mit_peaks_an(client):
    rec = _upload(client)
    rid = rec["uid"]  # Routen nutzen die String-UID, nicht die numerische id

    # Peaks am Original setzen (wie nach erfolgreicher Berechnung)
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])  # numerische id fürs DB-Fetch
        assert r is not None
        r.waveform_peaks = [0.1, 0.2, 0.3]
        s.add(r)
        s.commit()

    resp = client.post(f"/api/recordings/{rid}/duplicate")
    assert resp.status_code == 201, resp.text
    dup = resp.json()

    assert dup["id"] != rid
    assert dup["original_name"] == "zoom.mp3"
    # Peaks vom Original übernommen — kein ffmpeg-Decode nötig
    assert dup.get("waveform_peaks") == [0.1, 0.2, 0.3]

    # Datei-Kopie existiert auf Platte und ist vom Original getrennt
    from app.config import settings
    from app.db import engine as eng2
    from app.models import Recording as Rec

    with Session(eng2) as s:
        orig = s.get(Rec, rec["id"])
        new = s.get(Rec, int(dup["id"]))
        assert orig is not None and new is not None
        assert orig.stored_path != new.stored_path
        assert Path(new.stored_path).is_file()
        assert Path(new.stored_path).read_bytes() == Path(orig.stored_path).read_bytes()
        assert settings.AUDIO_DIR == Path(new.stored_path).parent


def test_duplicate_unbekannt_404(client):
    resp = client.post("/api/recordings/doesnotexist/duplicate")
    assert resp.status_code == 404
