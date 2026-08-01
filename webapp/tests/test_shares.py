"""Share-API-Tests (Task A3) — Router-Funktionen direkt, echte SQLite-DB."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Recording, RecordingShare, User
from app.routers import shares


class _FakeRequest:
    def __init__(self, session=None, oidc_enabled=True):
        self.session = session or {}
        self._oidc = oidc_enabled


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="owner", preferred_username="alice", email="a@x.de"))
        s.add(User(id=2, sub="other", preferred_username="bob", email="b@x.de"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="/tmp/a",
                        user_id=1))
        s.add(Recording(id=2, uid="r2", original_name="b.mp3", stored_path="/tmp/b",
                        user_id=2))
        s.commit()
    return eng


@pytest.fixture(autouse=True)
def _patch_current_user(monkeypatch):
    """Direkte User-Auflösung aus dem Fake-Request (unabhängig von Env)."""
    monkeypatch.setattr(shares, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


def _owner_req():
    return _FakeRequest(session={"user_id": 1})


def _anon_req():
    return _FakeRequest(session={}, oidc_enabled=False)


def _get(session, model, **kw):
    return session.exec(select(model).where(*[getattr(model, k) == v for k, v in kw.items()])).first()


def test_owner_can_share(db):
    with Session(db) as s:
        r = shares.create_share("r1", shares.ShareCreate(user="bob", level="write"),
                                _owner_req(), s)
        assert r["level"] == "write"
        assert _get(s, RecordingShare, rec_id=1, user_id=2) is not None


def test_share_by_email(db):
    with Session(db) as s:
        r = shares.create_share("r1", shares.ShareCreate(user="b@x.de", level="read"),
                                _owner_req(), s)
        assert r["user_id"] == 2


def test_non_owner_cannot_share(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            shares.create_share("r2", shares.ShareCreate(user="bob", level="read"),
                                _owner_req(), s)
        assert ei.value.status_code == 403


def test_unknown_user_404(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            shares.create_share("r1", shares.ShareCreate(user="nobody", level="read"),
                                _owner_req(), s)
        assert ei.value.status_code == 404


def test_cannot_share_to_owner(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            shares.create_share("r1", shares.ShareCreate(user="alice", level="read"),
                                _owner_req(), s)
        assert ei.value.status_code == 409


def test_unknown_recording_404(db):
    with Session(db) as s:
        with pytest.raises(HTTPException):
            shares.create_share("nope", shares.ShareCreate(user="bob", level="read"),
                                _owner_req(), s)


def test_list_shares(db):
    with Session(db) as s:
        shares.create_share("r1", shares.ShareCreate(user="bob", level="write"),
                            _owner_req(), s)
    with Session(db) as s:
        lst = shares.list_shares("r1", _owner_req(), s)
        assert len(lst) == 1 and lst[0]["user_name"] == "bob" and lst[0]["level"] == "write"


def test_update_level(db):
    with Session(db) as s:
        r = shares.create_share("r1", shares.ShareCreate(user="bob", level="read"),
                                _owner_req(), s)
        sid = r["share_id"]
    with Session(db) as s:
        up = shares.update_share("r1", sid, shares.ShareUpdate(level="full"), _owner_req(), s)
        assert up["level"] == "full"


def test_delete_share(db):
    with Session(db) as s:
        r = shares.create_share("r1", shares.ShareCreate(user="bob", level="read"),
                                _owner_req(), s)
        sid = r["share_id"]
    with Session(db) as s:
        shares.delete_share("r1", sid, _owner_req(), s)
        assert _get(s, RecordingShare, rec_id=1, user_id=2) is None


def test_anon_cannot_share_legacy_public(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            shares.create_share("r1", shares.ShareCreate(user="bob", level="read"),
                                _anon_req(), s)
        assert ei.value.status_code == 403
