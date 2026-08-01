"""API-Keys (Task C1/C2) — Modell (nur Hash) + CRUD (Owner-only, Token einmalig)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import ApiKey, User, hash_token
from app.routers import keys


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(keys, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="a"))
        s.add(User(id=2, sub="b"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def test_create_returns_token_once(db):
    with Session(db) as s:
        r = keys.create_key(keys.KeyCreate(name="mein-skript", level="write"),
                            _req(1), s)
        assert r["token"]
        assert r["level"] == "write"
        assert r["name"] == "mein-skript"


def test_create_stores_hash_only(db):
    with Session(db) as s:
        r = keys.create_key(keys.KeyCreate(name="x", level="read"), _req(1), s)
        row = s.exec(select(ApiKey)).first()
        assert row.token_hash == hash_token(r["token"])
        assert r["token"] not in row.token_hash
        assert "token" not in keys.list_keys(_req(1), s)[0]


def test_list_only_own_keys(db):
    with Session(db) as s:
        keys.create_key(keys.KeyCreate(name="a", level="read"), _req(1), s)
        keys.create_key(keys.KeyCreate(name="b", level="read"), _req(2), s)
        lst = keys.list_keys(_req(1), s)
        assert len(lst) == 1 and lst[0]["name"] == "a"


def test_cannot_manage_foreign_key(db):
    with Session(db) as s:
        r = keys.create_key(keys.KeyCreate(name="a", level="read"), _req(1), s)
        kid = r["key_id"]
        with pytest.raises(HTTPException) as ei:
            keys.delete_key(kid, _req(2), s)
        assert ei.value.status_code == 404


def test_update_level(db):
    with Session(db) as s:
        r = keys.create_key(keys.KeyCreate(name="a", level="read"), _req(1), s)
        up = keys.update_key(r["key_id"], keys.KeyUpdate(level="full"), _req(1), s)
        assert up["level"] == "full"


def test_revoke_makes_key_gone(db):
    with Session(db) as s:
        r = keys.create_key(keys.KeyCreate(name="a", level="read"), _req(1), s)
        keys.delete_key(r["key_id"], _req(1), s)
        assert s.exec(select(ApiKey)).first() is None


def test_invalid_level_422():
    with pytest.raises(Exception):
        keys.KeyCreate(name="x", level="admin")


def test_unauth_401(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            keys.create_key(keys.KeyCreate(), _req(None), s)
        assert ei.value.status_code == 401


def test_hash_token_deterministic():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
