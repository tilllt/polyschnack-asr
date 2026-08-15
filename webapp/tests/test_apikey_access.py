"""API-Key-Zugriff (Task C3) — Bearer-Auth + Rechte-Deckel über die Routen."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import ApiKey, Recording, User, hash_token
from app.routers import recordings, segments


class _FakeRequest:
    def __init__(self, headers=None, session=None):
        self.headers = headers or {}
        self.session = session or {}


@pytest.fixture(autouse=True)
def _oidc(monkeypatch):
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"X")
    with Session(eng) as s:
        s.add(User(id=1, sub="owner", kind="oidc"))
        s.add(User(id=2, sub="bob", kind="oidc"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1, status="done", text="Hallo",
                        segments=[{"start": 0.0, "end": 1.0, "text": "Hallo"}]))
        s.add(ApiKey(id=1, user_id=1, name="read-key", level="read",
                     token_hash=hash_token("tok-read")))
        s.add(ApiKey(id=2, user_id=1, name="write-key", level="write",
                     token_hash=hash_token("tok-write")))
        s.add(ApiKey(id=3, user_id=1, name="full-key", level="full",
                     token_hash=hash_token("tok-full")))
        s.add(ApiKey(id=4, user_id=2, name="bob-key", level="read",
                     token_hash=hash_token("tok-bob")))
        s.commit()
    return eng


def _bearer(token):
    return _FakeRequest(headers={"Authorization": f"Bearer {token}"})


def test_bearer_read_access(db):
    with Session(db) as s:
        d = recordings.get_recording_endpoint("r1", _bearer("tok-read"), s)
        assert d["uid"] == "r1"
        assert d["access_level"] == "read"  # Cap sichtbar


def test_bearer_read_cannot_edit(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            segments.update_segment("r1", 0, segments.SegmentUpdate(text="X"),
                                    _bearer("tok-read"), s)
        assert ei.value.status_code == 403


def test_bearer_write_can_edit(db):
    with Session(db) as s:
        d = segments.update_segment("r1", 0, segments.SegmentUpdate(text="Geändert"),
                                    _bearer("tok-write"), s)
        assert d["segments"][0]["text"] == "Geändert"


def test_bearer_full_can_delete(db):
    with Session(db) as s:
        d = recordings.delete_recording_endpoint("r1", _bearer("tok-full"), s)
        assert d["deleted"] == "r1"
        assert s.get(Recording, 1) is None


def test_invalid_token_401(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_recording_endpoint("r1", _bearer("wrong"), s)
        assert ei.value.status_code == 401


def test_revoked_key_401(db):
    with Session(db) as s:
        s.delete(s.get(ApiKey, 1))
        s.commit()
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_recording_endpoint("r1", _bearer("tok-read"), s)
        assert ei.value.status_code == 401


def test_expired_key_401(db):
    from datetime import datetime, timedelta, timezone

    with Session(db) as s:
        k = s.get(ApiKey, 1)
        k.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        s.add(k)
        s.commit()
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_recording_endpoint("r1", _bearer("tok-read"), s)
        assert ei.value.status_code == 401
        assert ei.value.detail == "API key expired"


def test_future_key_ok(db):
    from datetime import datetime, timedelta, timezone

    with Session(db) as s:
        k = s.get(ApiKey, 1)
        k.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        s.add(k)
        s.commit()
    with Session(db) as s:
        d = recordings.get_recording_endpoint("r1", _bearer("tok-read"), s)
        assert d["uid"] == "r1"


def test_no_token_falls_back_to_session(db):
    # Ohne Bearer: OIDC-Session-Owner hat full (kein Cap)
    with Session(db) as s:
        d = recordings.get_recording_endpoint(
            "r1", _FakeRequest(session={"user_id": 1}), s)
        assert d["access_level"] == "full"


def test_foreign_key_no_access(db):
    # bobs read-Key (user_id=2) hat keinen Zugriff auf r1 (owner=1)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_recording_endpoint("r1", _bearer("tok-bob"), s)
        assert ei.value.status_code == 403
