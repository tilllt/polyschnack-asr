"""Admin-Rolle (Task 1): Env-basierte Admin-Erkennung, kein DB-Feld.

- ``_is_admin``: sub/email in POLYSCHNACK_ADMINS ODER Gruppen-Intersection mit POLYSCHNACK_ADMIN_GROUPS.
- ``require_admin``: FastAPI-Dependency, 403 wenn nicht Admin; deaktiviert ohne OIDC.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import settings
from app.deps import require_admin
from app.routers.auth import _is_admin


class _FakeUser:
    def __init__(self, sub="u1", email=None, name="Max"):
        self.sub = sub
        self.email = email
        self.name = name
        self.preferred_username = None


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


# ---------------------------------------------------------------- _is_admin

def test_admin_by_sub(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "u1, u2@example.com")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    assert _is_admin({}, _FakeUser(sub="u1")) is True


def test_admin_by_email(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "u1, u2@example.com")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    assert _is_admin({}, _FakeUser(sub="x", email="u2@example.com")) is True


def test_admin_by_group(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "polyschnack-admins")
    assert _is_admin({"groups": ["users", "polyschnack-admins"]}, _FakeUser()) is True


def test_not_admin(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "admins")
    assert _is_admin({"groups": ["users"]}, _FakeUser()) is False
    assert _is_admin({}, _FakeUser()) is False


# ------------------------------------------------------------ require_admin

def test_require_admin_ok(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    require_admin(_FakeRequest(session={"is_admin": True}))


def test_require_admin_403_without_flag(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    with pytest.raises(HTTPException) as ei:
        require_admin(_FakeRequest(session={}))
    assert ei.value.status_code == 403


def test_require_admin_403_when_oidc_disabled(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    with pytest.raises(HTTPException) as ei:
        require_admin(_FakeRequest(session={"is_admin": True}))
    assert ei.value.status_code == 403


# -------------------------------------------------- /auth/me frisch (2026-08-14)
#
# Der Admin-Status wird beim Login in die Session gecacht. Damit Änderungen
# an POLYSCHNACK_ADMINS sofort wirken (ohne Logout/Login), berechnet
# /auth/me ihn bei jedem Aufruf FRISCH gegen die Env und schreibt ihn in
# die Session zurück (require_admin bleibt konsistent).

class _FakeSessionCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _call_me(monkeypatch, session, user):
    from app.routers import auth as auth_mod

    monkeypatch.setattr(auth_mod, "get_session", lambda: iter([_FakeSessionCtx()]))
    monkeypatch.setattr(
        "app.crud.get_user", lambda s, uid: user
    )
    req = _FakeRequest(session=session)
    return auth_mod.me(req), req


def test_me_admin_frisch_trotz_altem_session_flag(monkeypatch):
    """Env enthält die sub, aber die Session hat noch is_admin=False
    (Login vor der Env-Änderung) → /auth/me liefert True und schreibt das
    Flag in die Session zurück."""
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "neu-sub, x@y.de")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    body, req = _call_me(
        monkeypatch,
        session={"user_id": 1, "is_admin": False, "groups": []},
        user=_FakeUser(sub="neu-sub"),
    )
    assert body["is_admin"] is True
    assert req.session["is_admin"] is True  # Rückgabe in Session


def test_me_admin_frisch_per_email(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "neu-sub, admin@cia-spandau.de")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    body, req = _call_me(
        monkeypatch,
        session={"user_id": 1, "is_admin": False, "groups": []},
        user=_FakeUser(sub="x", email="admin@cia-spandau.de"),
    )
    assert body["is_admin"] is True


def test_me_admin_frisch_per_gruppe(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "polyschnack-admins")
    body, req = _call_me(
        monkeypatch,
        session={"user_id": 1, "is_admin": False, "groups": ["polyschnack-admins"]},
        user=_FakeUser(sub="x"),
    )
    assert body["is_admin"] is True
    assert req.session["is_admin"] is True


def test_me_bleibt_nicht_admin(monkeypatch):
    """Env ohne die sub → frisch False, Session-Flag bleibt False."""
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMINS", "anderer-user")
    monkeypatch.setattr(settings, "POLYSCHNACK_ADMIN_GROUPS", "")
    body, req = _call_me(
        monkeypatch,
        session={"user_id": 1, "is_admin": False, "groups": []},
        user=_FakeUser(sub="neu-sub"),
    )
    assert body["is_admin"] is False
    assert req.session["is_admin"] is False
