"""Prompt-Templates + Delivery-Targets (Task D2/D3) — CRUD, Verschlüsselung."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.crypto import decrypt, encrypt
from app.models import DeliveryTarget, User
from app.routers import targets, templates


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(templates, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    monkeypatch.setattr(targets, "_current_user",
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


def test_template_crud(db):
    with Session(db) as s:
        r = templates.create_template(
            templates.TemplateCreate(name="meeting", prompt="Fasse zusammen"),
            _req(1), s)
        lst = templates.list_templates(_req(1), s)
        assert len(lst) == 1 and lst[0]["name"] == "meeting"
        up = templates.update_template(
            r["template_id"], templates.TemplateUpdate(prompt="Neu"), _req(1), s)
        assert up["prompt"] == "Neu"
        templates.delete_template(r["template_id"], _req(1), s)
        assert templates.list_templates(_req(1), s) == []


def test_template_foreign_forbidden(db):
    with Session(db) as s:
        r = templates.create_template(
            templates.TemplateCreate(name="a", prompt="x"), _req(1), s)
        with pytest.raises(HTTPException) as ei:
            templates.update_template(r["template_id"],
                                      templates.TemplateUpdate(prompt="y"), _req(2), s)
        assert ei.value.status_code == 404


def test_crypto_roundtrip():
    plain = "geheim123"
    cipher = encrypt(plain)
    assert cipher != plain
    assert plain not in cipher
    assert decrypt(cipher) == plain


def test_webdav_password_encrypted_in_db(db):
    with Session(db) as s:
        r = targets.create_target(
            targets.TargetCreate(name="nc", kind="webdav",
                                 config={"url": "https://dav.example",
                                         "username": "u", "password": "pw",
                                         "path": "/ziel"}),
            _req(1), s)
        row = s.get(DeliveryTarget, r["target_id"])
        stored = row.config
        # Kein Substring-Check auf "pw": Fernet-Tokens sind Base64 und können
        # zufällig "pw" enthalten (Schlüssel-abhängig -> CI-flaky). Robust:
        stored_cfg = __import__("json").loads(stored)
        assert stored_cfg["password"] != "pw"                  # nicht Klartext
        assert stored_cfg["password"].startswith("gAAAAA")     # Fernet-Token
        assert "password" not in r["config"] or r["config"]["password"] == "********"
        assert decrypt(stored_cfg["password"]) == "pw"


def test_email_target_roundtrip(db):
    with Session(db) as s:
        r = targets.create_target(
            targets.TargetCreate(name="mail", kind="email", config={"to": "x@y.de"}),
            _req(1), s)
        assert r["config"]["to"] == "x@y.de"
        lst = targets.list_targets(_req(1), s)
        assert lst[0]["kind"] == "email"


def test_target_foreign_forbidden(db):
    with Session(db) as s:
        r = targets.create_target(
            targets.TargetCreate(name="a", kind="email", config={"to": "x@y.de"}),
            _req(1), s)
        with pytest.raises(HTTPException):
            targets.delete_target(r["target_id"], _req(2), s)


def test_invalid_kind_422():
    with pytest.raises(Exception):
        targets.TargetCreate(name="x", kind="ftp", config={})


def test_anonymous_cannot_create_template(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            templates.create_template(
                templates.TemplateCreate(name="a", prompt="x"), _req(None), s)
        assert ei.value.status_code == 403
