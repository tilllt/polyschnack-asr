"""/auth/me muss für anonyme User Name (display_name) UND die
Retention-Information liefern — das Frontend zeigt daraus den
Hinweis „Dateien werden nach X Minuten gelöscht"."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'me.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", False)  # anon-Pfad aktiv
    with TestClient(app) as c:
        yield c


def test_me_anon_liefert_name_und_retention(client, monkeypatch):
    """Anon-User bekommt display_name + retention_minutes vom /auth/me."""
    from app.config import settings

    monkeypatch.setattr(settings, "POLYSCHNACK_ANON_RETENTION_MINUTES", 15)
    r = client.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body.get("anonymous") is True
    assert body.get("name"), "anon-User braucht einen Dummy-Namen"
    assert " " in body["name"], "Name soll aus mehreren Wörtern bestehen"
    assert body.get("retention_minutes") == 15


def test_me_anon_retention_folgt_config(client, monkeypatch):
    """retention_minutes spiegelt die Config (nicht hartkodiert)."""
    from app.config import settings

    monkeypatch.setattr(settings, "POLYSCHNACK_ANON_RETENTION_MINUTES", 7)
    r = client.get("/auth/me")
    assert r.json().get("retention_minutes") == 7


def test_me_anon_name_stabil_pro_session(client):
    """Zwei Abrufe derselben Session → gleicher Name (kein Neu-Würfeln)."""
    r1 = client.get("/auth/me").json()
    r2 = client.get("/auth/me").json()
    assert r1["name"] == r2["name"]


def test_me_oidc_keine_retention_angabe(client, monkeypatch):
    """Eingeloggte OIDC-User bekommen keine anon-Retention (irrelevant).

    Wir testen den OIDC-Pfad von /auth/me direkt (Funktionsebene) mit
    einem Fake-Request — das Session-Signing selbst ist Starlette-Sache.
    """
    from app.config import settings
    from app.db import engine
    from app.models import User
    from sqlmodel import Session

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    with Session(engine) as s:
        s.add(User(id=1, sub="oidc-1", kind="oidc", name="Max Mustermann"))
        s.commit()

    from app.routers.auth import me

    class _FakeRequest:
        session = {"user_id": 1}

    body = me(_FakeRequest())
    assert body.get("authenticated") is True
    assert "retention_minutes" not in body


def test_me_anon_auch_bei_oidc_aktiv(client, monkeypatch):
    """PROD-BUG-Fix: Anon-User bekommen Name+Retention AUCH bei
    OIDC_ENABLED (kein Login) — vorher kam nur {authenticated: False}."""
    from app.config import settings
    from app.routers.auth import me

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(settings, "POLYSCHNACK_ANON_RETENTION_MINUTES", 15)

    class _FakeRequest:
        session = {}

    body = me(_FakeRequest())
    assert body.get("anonymous") is True
    assert body.get("name")
    assert body.get("retention_minutes") == 15
