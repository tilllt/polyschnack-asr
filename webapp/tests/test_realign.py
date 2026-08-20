"""Change 046: Re-Align-Endpoint POST /api/recordings/{rid}/realign.

Der User hat die Transkription korrigiert (Ground Truth) → Forced-Aligner
verifiziert die Word-Timestamps erneut. Auth (write), status=done, Aligner
deaktiviert/Audio fehlt → verständliche Fehler. Der echte Worker
(_schedule_realign) wird gemockt — Thread-Start ist in test_aligner.py
abgedeckt.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import Recording, User


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app import deps
    from app.identity import Identity
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'realign.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    # `from .db import engine` bindet beim IMPORT — Module, die die Engine
    # bereits importiert haben (queue, service), müssen direkt gemockt
    # werden; main.py importiert lokal (nutzt den db-Mock automatisch).
    import app.queue as queue_mod
    import app.service as svc_mod

    monkeypatch.setattr(queue_mod, "engine", eng)
    monkeypatch.setattr(svc_mod, "engine", eng)
    with Session(eng) as s:
        s.add(User(id=77, sub="realign-tester", kind="oidc"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=9, uid="rec-realign-1", original_name="a.mp3",
            stored_path=str(audio), user_id=77, status="done",
            text="Hallo Welt",
            segments=[{"start": 0.0, "end": 1.0, "text": "Hallo Welt",
                       "words": [{"word": "Hallo", "start": 0.0, "end": 0.4},
                                 {"word": "Welt", "start": 0.4, "end": 1.0}]}],
        ))
        s.add(Recording(
            id=10, uid="rec-realign-queued", original_name="b.mp3",
            stored_path=str(audio), user_id=77, status="queued",
        ))
        s.commit()

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)

    def _fake_oidc(request, session):
        return Identity(User(id=77, sub="realign-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)

    # Worker nicht wirklich starten — nur den Scheduler prüfen.
    from app import service as svc

    monkeypatch.setattr(svc, "_schedule_realign", lambda rec_id: True)

    with TestClient(app) as c:
        yield c


def test_realign_startet_worker(client):
    r = client.post("/api/recordings/rec-realign-1/realign")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "rec-realign-1"
    assert body["alignment"] == "pending"


def test_realign_nur_done(client):
    r = client.post("/api/recordings/rec-realign-queued/realign")
    assert r.status_code == 409
    assert "noch nicht fertig" in r.json()["detail"]


def test_realign_404(client):
    r = client.post("/api/recordings/unbekannt/realign")
    assert r.status_code == 404


def test_realign_503_wenn_scheduler_ablehnt(client, monkeypatch):
    from app import service as svc

    monkeypatch.setattr(svc, "_schedule_realign", lambda rec_id: False)
    r = client.post("/api/recordings/rec-realign-1/realign")
    assert r.status_code == 503
    assert "Re-Alignment nicht möglich" in r.json()["detail"]
