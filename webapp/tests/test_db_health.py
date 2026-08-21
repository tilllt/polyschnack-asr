"""Tests für Change 067 — DB-Erreichbarkeit sichtbar machen.

- /health meldet db-Status (SELECT 1)
- SQLAlchemy-Fehler in Daten-Routen → 503 mit klarer Meldung statt
  stille leerer Ergebnisse (Vorfall 2026-08-21)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="db_health_test_")
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("BENCHMARK_API_KEYS", "test-key-123")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from app import db as db_module
    from app.main import app
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(f"sqlite:///{tmp_path / 'h.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "h.db")
    with TestClient(app) as c:
        yield c


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["db"]["ok"] is True
    assert d["db"]["error"] == ""


def test_db_error_yields_503_instead_of_silent_empty(client, monkeypatch):
    """Change 067: DB-Fehler → 503 mit Meldung, nicht stille Nullwerte."""
    from sqlalchemy.exc import OperationalError

    class _BrokenSession:
        def exec(self, *a, **k):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def get(self, *a, **k):
            raise OperationalError("SELECT", {}, Exception("db down"))

    from app import db as db_module
    from sqlalchemy import event

    # Engine so brechen, dass jede Session-Erstellung wirft
    orig_connect = db_module.engine.connect

    def _broken_connect():
        raise OperationalError("connect", {}, Exception("sqlite file not reachable"))

    monkeypatch.setattr(db_module.engine, "connect", _broken_connect)
    r = client.get("/api/recordings")
    assert r.status_code == 503
    assert "Datenbank nicht erreichbar" in r.json()["detail"]
    monkeypatch.setattr(db_module.engine, "connect", orig_connect)


def test_stats_503_on_db_failure(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def _broken_connect():
        raise OperationalError("connect", {}, Exception("db down"))

    from app import db as db_module

    monkeypatch.setattr(db_module.engine, "connect", _broken_connect)
    r = client.get("/api/stats")
    assert r.status_code == 503
    assert "Datenbank nicht erreichbar" in r.json()["detail"]
