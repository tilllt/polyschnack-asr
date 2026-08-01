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
    def __init__(self, sub="u1", email=None):
        self.sub = sub
        self.email = email


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
