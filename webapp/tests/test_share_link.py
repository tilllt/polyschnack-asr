"""Anon-Share-Link (read-only): Owner aktiviert share_token → jeder mit
dem 32-Zeichen-UID-Link kann die Transkription lesen (ohne Login).

- NUR read: Edit/Re-Transcribe/Delete bleiben blockiert (401/403)
- Versions-Gating: Versionen VOR shared_at sind unsichtbar (discarded)
- Nach Retention-Sweep: Link 404
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import Recording, TranscriptVersion, User


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module

    eng = create_engine(f"sqlite:///{tmp_path / 'share.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.db import init_db

    init_db()  # _auto_migrate: fügt share_token/shared_at hinzu falls fehlt
    return eng


@pytest.fixture()
def client(db, monkeypatch):
    from app import deps
    from app.identity import Identity
    from app.main import app
    import app.identity as identity_mod

    def _fake_oidc(request, session):
        return Identity(User(id=1, sub="owner", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def anon_rec(db):
    """Recording des Owners mit share_token=True + shared_at gesetzt."""
    from sqlmodel import Session

    with Session(db) as s:
        s.add(User(id=1, sub="owner", kind="oidc"))
        audio = Path(db.url.database).parent / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=1, uid="anon-uid", original_name="a.mp3",
            stored_path=str(audio), user_id=1, status="done",
            text="Hallo Welt", share_token=True,
            # SQLite speichert naive datetimes — shared_at bewusst OHNE tzinfo
            shared_at=dt.datetime(2026, 8, 2, 12, 0),
            segments=[{"start": 0.0, "end": 2.0, "text": "Hallo Welt"}],
        ))
        s.commit()


@pytest.fixture()
def private_rec(db):
    """Recording OHNE share_token — bleibt geschützt."""
    from sqlmodel import Session

    with Session(db) as s:
        s.add(User(id=1, sub="owner", kind="oidc"))
        audio = Path(db.url.database).parent / "p.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=2, uid="private-uid", original_name="p.mp3",
            stored_path=str(audio), user_id=1, status="done", text="Geheim",
        ))
        s.commit()


def test_anon_link_toggle_on(client, db):
    from sqlmodel import Session

    with Session(db) as s:
        s.add(User(id=1, sub="owner", kind="oidc"))
        audio = Path(db.url.database).parent / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(id=3, uid="rec-uid", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="done"))
        s.commit()
    r = client.post("/api/recordings/rec-uid/anon-link", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["share_token"] is True
    assert r.json()["shared_at"] is not None


def test_anon_link_toggle_off(client, anon_rec):
    r = client.post("/api/recordings/anon-uid/anon-link", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["share_token"] is False


def test_anon_link_readable_without_login(client, anon_rec):
    """Ohne Login (OIDC aus) kann jeder den Link lesen."""
    from app.config import settings

    settings.OIDC_ENABLED = False
    # Identität aushebeln: anon-Pfad ohne Login
    import app.routers.recordings as rec_mod

    class _Anon:
        key_level = None

        @property
        def user(self):
            return None

    orig = rec_mod._current_user
    rec_mod._current_user = lambda request, session=None: None
    try:
        r = client.get("/api/recordings/anon-uid")
        assert r.status_code == 200
        assert r.json()["uid"] == "anon-uid"
        assert r.json()["is_anon_shared"] is True
    finally:
        rec_mod._current_user = orig


def test_no_token_recording_requires_auth(client, private_rec):
    """Ohne share_token: kein öffentlicher Zugriff."""
    from app.config import settings

    settings.OIDC_ENABLED = False
    import app.routers.recordings as rec_mod

    orig = rec_mod._current_user
    rec_mod._current_user = lambda request, session=None: None
    try:
        r = client.get("/api/recordings/private-uid")
        assert r.status_code in (401, 403)
    finally:
        rec_mod._current_user = orig


def test_anon_link_audio_readable(client, anon_rec):
    from app.config import settings

    settings.OIDC_ENABLED = False
    import app.routers.recordings as rec_mod

    orig = rec_mod._current_user
    rec_mod._current_user = lambda request, session=None: None
    try:
        r = client.get("/api/recordings/anon-uid/audio")
        assert r.status_code == 200
    finally:
        rec_mod._current_user = orig


def test_anon_link_edit_blocked(client, anon_rec):
    """read-only: PATCH segments → 403 für Anon ohne Login."""
    from app.config import settings

    settings.OIDC_ENABLED = False
    import app.routers.segments as seg_mod
    import app.identity as identity_mod

    orig = identity_mod.current_identity
    identity_mod.current_identity = lambda request, session: None
    try:
        r = client.patch("/api/recordings/anon-uid/segments/0",
                         json={"text": "neu"})
        assert r.status_code in (401, 403)
    finally:
        identity_mod.current_identity = orig


def test_anon_link_retranscribe_blocked(client, anon_rec):
    from app.config import settings

    settings.OIDC_ENABLED = False
    import app.routers.recordings as rec_mod

    orig = rec_mod._current_user
    rec_mod._current_user = lambda request, session=None: None
    try:
        r = client.post("/api/recordings/anon-uid/retranscribe")
        assert r.status_code in (401, 403)
    finally:
        rec_mod._current_user = orig


def test_anon_link_delete_blocked(client, anon_rec):
    from app.config import settings

    settings.OIDC_ENABLED = False
    import app.routers.recordings as rec_mod

    orig = rec_mod._current_user
    rec_mod._current_user = lambda request, session=None: None
    try:
        r = client.delete("/api/recordings/anon-uid")
        assert r.status_code in (401, 403)
    finally:
        rec_mod._current_user = orig


def test_anon_link_versions_gated_since_shared_at(client, anon_rec):
    """Versionen VOR shared_at sind für Anon unsichtbar (discarded)."""
    from app.config import settings
    from sqlmodel import Session

    settings.OIDC_ENABLED = False
    with Session(db := __import__("app.db", fromlist=["engine"]).engine) as s:
        s.add(TranscriptVersion(
            rec_id=1, version_no=1, kind="transcribe", text="Alt",
            created_at=dt.datetime(2026, 8, 1, 10, 0),  # naive (SQLite-Stil)
        ))
        s.add(TranscriptVersion(
            rec_id=1, version_no=2, kind="edit", text="Neu",
            created_at=dt.datetime(2026, 8, 2, 13, 0),
        ))
        s.commit()

    import app.identity as identity_mod

    orig = identity_mod.current_identity
    identity_mod.current_identity = lambda request, session: None
    try:
        r = client.get("/api/recordings/anon-uid/versions")
        assert r.status_code == 200
        vs = r.json()
        nos = [v["version_no"] for v in vs]
        assert 2 in nos
        assert 1 not in nos  # v1 (vor Share) discarded
    finally:
        identity_mod.current_identity = orig
