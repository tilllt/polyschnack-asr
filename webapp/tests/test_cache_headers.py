"""Change 212 — Cache-Header (Nutzer-Befund 19.09.2026).

Nach einem Deploy zeigte das Handy weiter den alten Stand: für die HTML-Seite
waren keine Cache-Header gesetzt, der Browser durfte also heuristisch lange
cachen. Die Regel ist jetzt ausdrücklich:

- HTML (`/`, alles mit content-type text/html): ``no-cache`` — jede Anfrage holt
  die aktuelle Version, damit ein Deploy sofort sichtbar ist.
- Gehashte Assets unter ``/assets/``: unbegrenzt cachebar und ``immutable`` —
  ihr Dateiname ändert sich mit dem Inhalt, ein erneutes Laden wäre verschwendet.

Die Header setzt dieselbe Middleware wie ``X-Robots-Tag``; sie gelten daher auch
für Antworten, die kein 200 sind (fehlende Asset-Datei).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Aufbau wie in tests/test_seo.py — dieselbe Middleware, eigene DB."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine  # noqa: F401

    from app import db as db_module
    from app.main import app

    eng = create_engine(
        f"sqlite:///{tmp_path / 'cache.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)

    with TestClient(app) as c:
        yield c


def test_root_html_ist_nicht_cachebar(client):
    resp = client.get("/")
    assert resp.headers.get("Cache-Control") == "no-cache, must-revalidate"
    assert resp.headers.get("Pragma") == "no-cache"


def test_assets_sind_lang_cachebar(client):
    resp = client.get("/assets/nicht-vorhanden-abcd1234.js")
    assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"


def test_assets_bekommen_nicht_die_html_regel(client):
    """Gegenprobe: Die Asset-Regel darf nicht versehentlich 'no-cache' tragen —
    sonst würden die gehashten Dateien bei jedem Aufruf neu geholt."""
    resp = client.get("/assets/nicht-vorhanden-abcd1234.js")
    assert "no-cache" not in (resp.headers.get("Cache-Control") or "")
