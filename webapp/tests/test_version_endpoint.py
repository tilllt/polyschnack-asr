"""Change 134: Build-Version-Endpunkte (/api/version, /version).

Prüft, dass die Webapp ihre Git-Commit-SHA aus der Build-Env GIT_SHA
ausliefert (Default "dev" ohne CI-Build) und dass der Endpunkt ohne
Auth erreichbar ist (wie /health).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(monkeypatch):
    return TestClient(app)


def test_api_version_liefert_dev_default(client):
    """Ohne GIT_SHA-Env (lokale Tests) → commit=dev."""
    r = client.get("/api/version")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "webapp"
    assert data["commit"] == "dev"
    assert data["image_tag"] == "dev"


def test_api_version_nimmt_git_sha_aus_env(client, monkeypatch):
    """Mit GIT_SHA-Env (CI-Build) → Commit-SHA wird ausgeliefert."""
    monkeypatch.setenv("GIT_SHA", "4a41b46e")
    r = client.get("/api/version")
    assert r.status_code == 200
    data = r.json()
    assert data["commit"] == "4a41b46e"
    assert data["image_tag"] == "4a41b46e"


def test_api_version_ist_ohne_auth_erreichbar(client):
    """Version ist öffentlich (wie /health) — kein Login nötig."""
    r = client.get("/api/version")
    assert r.status_code == 200
    assert "commit" in r.json()
