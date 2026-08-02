"""Settings-APIs (Templates/Targets/BYOK) sind OIDC-only (User-Forderung 01.08.).

Anon-User (OIDC aktiv) bekommen 403 auf /api/templates, /api/targets und
/api/llm-endpoints; eingeloggte OIDC-User behalten vollen Zugriff.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:  # lifespan -> init_db()
        yield c


def _oidc_an(client, monkeypatch):
    """OIDC an, kein Login -> anon-Session (echter Pfad)."""
    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    assert client.get("/api/stats").status_code == 200


def _oidc_login(client, monkeypatch):
    """OIDC an + eingeloggte Identität.

    Session-Cookie ist signiert (zufälliges Test-Secret) -> statt Cookie-Fake
    wird current_identity gemockt (Repo-Muster wie _current_user in anderen
    Tests). Das Gating selbst (kind-Check) bleibt der echte Code.
    """
    from app import deps
    from app.identity import Identity
    from app.models import User

    monkeypatch.setattr(settings := __import__("app.config", fromlist=["settings"]).settings,
                        "OIDC_ENABLED", True)

    def _fake_oidc(request, session):
        return Identity(User(id=4242, sub="oidc-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    return _fake_oidc


def test_anon_kein_template_zugriff(client, monkeypatch):
    _oidc_an(client, monkeypatch)
    r = client.get("/api/templates")
    assert r.status_code in (401, 403), f"anon darf keine Templates sehen: {r.status_code}"


def test_anon_kein_target_zugriff(client, monkeypatch):
    _oidc_an(client, monkeypatch)
    r = client.get("/api/targets")
    assert r.status_code in (401, 403), f"anon darf keine Targets sehen: {r.status_code}"


def test_anon_kein_endpoint_zugriff(client, monkeypatch):
    _oidc_an(client, monkeypatch)
    r = client.get("/api/llm-endpoints")
    assert r.status_code in (401, 403), f"anon darf keine Endpoints sehen: {r.status_code}"


def test_eingeloggter_user_sieht_templates(client, monkeypatch):
    _oidc_login(client, monkeypatch)
    r = client.get("/api/templates")
    assert r.status_code == 200, f"eingeloggter User: {r.status_code} {r.text[:200]}"


def test_eingeloggter_user_sieht_targets(client, monkeypatch):
    _oidc_login(client, monkeypatch)
    r = client.get("/api/targets")
    assert r.status_code == 200, f"eingeloggter User: {r.status_code} {r.text[:200]}"


def test_eingeloggter_user_sieht_endpoints(client, monkeypatch):
    _oidc_login(client, monkeypatch)
    r = client.get("/api/llm-endpoints")
    assert r.status_code == 200, f"eingeloggter User: {r.status_code} {r.text[:200]}"


def test_oidc_aus_weiterhin_offen(client, monkeypatch):
    """OIDC aus (Dev/Test): Routen bleiben für anon erreichbar."""
    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    for path in ("/api/templates", "/api/targets", "/api/llm-endpoints"):
        r = client.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code}"
