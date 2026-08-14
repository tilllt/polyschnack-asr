"""Settings-Seite: /auth/me liefert User-Basisinfos (email, groups, ...)
und /api/stats den genutzten Speicher (total_size_bytes)."""

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
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'settings.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    with TestClient(app) as c:
        yield c


def _add_user(engine, *, uid: int, sub: str, email=None, username=None):
    from app.models import User
    from sqlmodel import Session

    with Session(engine) as s:
        s.add(User(id=uid, sub=sub, kind="oidc", name="Max Mustermann",
                   email=email, preferred_username=username))
        s.commit()


def test_me_liefert_email_gruppen_und_username(client, monkeypatch):
    """Settings-Konto-Block: email + OIDC-groups + preferred_username."""
    from app.config import settings
    from app.db import engine
    from app.routers.auth import me

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "oidc-1")  # frisch aus Env
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    _add_user(engine, uid=1, sub="oidc-1", email="max@example.org",
              username="max")

    class _FakeRequest:
        session = {"user_id": 1, "is_admin": True,
                   "groups": ["admins", "team-a"]}

    body = me(_FakeRequest())
    assert body["authenticated"] is True
    assert body["email"] == "max@example.org"
    assert body["preferred_username"] == "max"
    assert body["groups"] == ["admins", "team-a"]
    assert body["is_admin"] is True


def test_me_ohne_gruppen_liefert_leere_liste(client, monkeypatch):
    """Keine Gruppen in der Session -> leere Liste (kein None)."""
    from app.config import settings
    from app.db import engine
    from app.routers.auth import me

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    _add_user(engine, uid=2, sub="oidc-2")

    class _FakeRequest:
        session = {"user_id": 2}

    body = me(_FakeRequest())
    assert body["groups"] == []


def test_stats_liefert_total_size_bytes(client):
    """Genutzter Speicher: Summe der size_bytes (Settings-Statistik)."""
    from app.crud import get_stats
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        for i, size in enumerate([1000, 2500, 500]):
            s.add(Recording(
                uid=f"r{i}", original_name=f"a{i}.mp3", stored_path=f"p{i}",
                size_bytes=size, status="done", duration_s=10.0,
            ))
        s.commit()

    stats = get_stats(Session(engine))
    assert stats["total"] == 3
    assert stats["total_size_bytes"] == 4000
    assert stats["done"] == 3


def test_stats_per_user_und_speicher(client):
    """Per-User-Filter: nur eigene Dateien + eigener Speicher."""
    from app.crud import get_stats
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        s.add(Recording(uid="mine", original_name="m.mp3", stored_path="m",
                        size_bytes=700, status="done", duration_s=5.0,
                        user_id=1))
        s.add(Recording(uid="other", original_name="o.mp3", stored_path="o",
                        size_bytes=9000, status="done", duration_s=5.0,
                        user_id=2))
        s.commit()

    stats = get_stats(Session(engine), user_id=1)
    assert stats["total"] == 1
    assert stats["total_size_bytes"] == 700
