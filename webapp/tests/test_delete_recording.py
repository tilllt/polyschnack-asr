"""Löschen entfernt ALLE Daten der Aufnahme (Datenschutz):

- Recording-Row, Audiodatei, Transkript-Versionen (komplette Texte!) und
  Shares müssen zusammen verschwinden — nichts darf in der DB zurückbleiben.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'del.db'}", connect_args={"check_same_thread": False})
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


def test_delete_entfernt_versionen_und_shares(client):
    rec = _upload(client)
    rid = rec["uid"]

    # Transkript-Version + Share in der DB anlegen (wie nach Transkription/Teilen)
    from app.db import engine
    from app.models import Recording, RecordingShare, TranscriptVersion
    from sqlmodel import Session

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r is not None
        r.text = "geheimer Inhalt"
        r.waveform_peaks = [0.1, 0.2]
        s.add(r)
        s.add(TranscriptVersion(rec_id=rec["id"], version_no=1, text="geheimer Inhalt"))
        s.add(RecordingShare(rec_id=rec["id"], user_id=1, level="full"))
        s.commit()

    # Löschen über den normalen Delete-Endpoint
    resp = client.delete(f"/api/recordings/{rid}")
    assert resp.status_code == 200, resp.text

    with Session(engine) as s:
        assert s.get(Recording, rec["id"]) is None
        assert (
            s.exec(
                select(TranscriptVersion).where(TranscriptVersion.rec_id == rec["id"])
            ).first()
            is None
        ), "TranscriptVersion blieb nach Delete zurück!"
        assert (
            s.exec(
                select(RecordingShare).where(RecordingShare.rec_id == rec["id"])
            ).first()
            is None
        ), "RecordingShare blieb nach Delete zurück!"

    # Audiodatei ist auch weg
    from app.config import settings

    assert list(Path(settings.AUDIO_DIR).iterdir()) == []


def test_delete_unbekannt_404(client):
    resp = client.delete("/api/recordings/doesnotexist")
    assert resp.status_code == 404
