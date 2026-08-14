"""Regressionstest: GET /api/stats darf mit OIDC aktiv nicht crashen.

Bug: stats_endpoint rief _current_user(request) OHNE session auf; dadurch
erreichte ensure_anonymous_user() ein None-Session-Objekt (AttributeError:
'NoneType' object has no attribute 'get') -> 500 bei jedem /api/stats-Request
auf der Produktionsinstanz. Alle anderen Routen übergeben die Session korrekt.
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


def test_stats_oidc_enabled_ohne_session_crash(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    # Kein Login -> anon-Session wird erzeugt; darf KEIN 500 werfen
    r = client.get("/api/stats")
    assert r.status_code == 200, f"erwartet 200, bekam {r.status_code}: {r.text[:200]}"


def test_stats_ohne_oidc(client, monkeypatch):
    """Ohne OIDC muss /api/stats sowieso 200 liefern."""
    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    r = client.get("/api/stats")
    assert r.status_code == 200
