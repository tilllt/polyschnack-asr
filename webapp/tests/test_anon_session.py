"""Anonyme Session-Identität (Task B3)."""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.anon_session import ensure_anonymous_user
from app.config import settings
from app.models import User


class _FakeRequest:
    def __init__(self, session=None, oidc_enabled=False):
        self.session = session or {}
        self._oidc = oidc_enabled


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(autouse=True)
def _oidc_off(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)


def test_first_visit_creates_anonymous_user(db):
    with Session(db) as s:
        req = _FakeRequest()
        u = ensure_anonymous_user(s, req)
        assert u.kind == "anonymous"
        assert u.display_name
        assert u.sub.startswith("anon:")
        assert req.session["anon_user_id"] == u.id
        assert "last_seen" in req.session
        assert u.last_seen_at is not None


def test_second_visit_reuses_user(db):
    with Session(db) as s:
        req = _FakeRequest()
        u1 = ensure_anonymous_user(s, req)
    with Session(db) as s:
        req2 = _FakeRequest(session={"anon_user_id": u1.id})
        u2 = ensure_anonymous_user(s, req2)
        assert u2.id == u1.id
        assert u2.display_name == u1.display_name


def test_stale_anon_id_creates_new_user(db):
    with Session(db) as s:
        req = _FakeRequest(session={"anon_user_id": 999})
        u = ensure_anonymous_user(s, req)
        assert u.id != 999
        assert u.kind == "anonymous"


def test_oidc_user_returns_directly(db, monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    with Session(db) as s:
        s.add(User(id=7, sub="oidc-sub", kind="oidc"))
        s.commit()
    with Session(db) as s:
        req = _FakeRequest(session={"user_id": 7}, oidc_enabled=True)
        u = ensure_anonymous_user(s, req)
        assert u.id == 7
        assert u.kind == "oidc"
        assert "anon_user_id" not in req.session
