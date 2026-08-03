"""Speaker-Rename: POST /api/recordings/{rid}/speaker-rename.

Ersetzt das speaker-Feld in ALLEN Segmenten (User-Anforderung: Doppelklick
auf einen Speaker-Namen → umbenennen → gilt an allen Vorkommen). Muster aus
test_segment_edit.py: eigene SQLite-DB, OIDC-User, Identity-Mocks an beiden
Import-Stellen (app.deps + app.identity).
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

    eng = create_engine(f"sqlite:///{tmp_path / 'rename.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    with Session(eng) as s:
        s.add(User(id=77, sub="rename-tester", kind="oidc"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=9, uid="rec-rename-1", original_name="a.mp3",
            stored_path=str(audio), user_id=77, status="done",
            text="a b c",
            segments=[
                {"start": 0.0, "end": 1.0, "text": "a", "speaker": "SPEAKER_00",
                 "words": [{"word": "a", "start": 0.0, "end": 1.0}]},
                {"start": 1.0, "end": 2.0, "text": "b", "speaker": "SPEAKER_01",
                 "words": [{"word": "b", "start": 1.0, "end": 2.0}]},
                {"start": 2.0, "end": 3.0, "text": "c", "speaker": "SPEAKER_00",
                 "words": [{"word": "c", "start": 2.0, "end": 3.0}]},
            ],
        ))
        s.commit()

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)

    def _fake_oidc(request, session):
        return Identity(User(id=77, sub="rename-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)

    with TestClient(app) as c:
        yield c


def test_rename_speaker_updates_all_segments(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    assert r.status_code == 200
    body = r.json()
    renamed = [s for s in body["segments"] if s["text"] in ("a", "c")]
    assert all(s["speaker"] == "Anna" for s in renamed)
    assert body["renamed"] == 2
    # Der andere Speaker bleibt unverändert
    other = [s for s in body["segments"] if s["text"] == "b"]
    assert other[0]["speaker"] == "SPEAKER_01"


def test_rename_speaker_unknown_returns_400(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_99", "to_speaker": "X"})
    assert r.status_code == 400


def test_rename_speaker_requires_auth(client, monkeypatch):
    from app import deps
    import app.identity as identity_mod

    monkeypatch.setattr(deps, "current_identity", lambda request, session: None)
    monkeypatch.setattr(identity_mod, "current_identity", lambda request, session: None)
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    assert r.status_code in (401, 403)


def test_rename_speaker_snapshots_version(client):
    from sqlmodel import Session

    from app import db as db_module
    from app.versions import list_versions

    client.post("/api/recordings/rec-rename-1/speaker-rename",
                json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    with Session(db_module.engine) as s:
        kinds = [v.kind for v in list_versions(s, 9)]
    assert "edit" in kinds


def test_rename_speaker_persists_after_reload(client):
    """Der neue Name steht auch in rec.segments (DB), nicht nur in der Antwort."""
    client.post("/api/recordings/rec-rename-1/speaker-rename",
                json={"from_speaker": "SPEAKER_00", "to_speaker": "Bernd"})
    r = client.get("/api/recordings/rec-rename-1")
    assert r.status_code == 200
    segs = r.json()["segments"]
    assert all(s["speaker"] == "Bernd" for s in segs if s["text"] in ("a", "c"))


def test_rename_speaker_empty_names_400(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "", "to_speaker": "X"})
    assert r.status_code == 400
    r2 = client.post("/api/recordings/rec-rename-1/speaker-rename",
                     json={"from_speaker": "SPEAKER_00", "to_speaker": "  "})
    assert r2.status_code == 400
