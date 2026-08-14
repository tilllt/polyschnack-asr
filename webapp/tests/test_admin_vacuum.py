"""Admin-VACUUM: POST /api/admin/vacuum kompaktiert die SQLite-DB.

Datenschutz: gelöschte Zeilen (Recordings, Versionen, Shares) sind nach
VACUUM nicht mehr physisch aus der DB-Datei lesbar. Nur Admins dürfen
triggern (require_admin)."""

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
    from app.config import settings
    from app.main import app

    db_file = tmp_path / "vacuum.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)

    # Admin-Gate für diesen Test freischalten (TestClient hat kein
    # session_transaction im httpx-Backend)
    from app.deps import require_admin

    app.dependency_overrides[require_admin] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_vacuum_admin_ok(client, tmp_path):
    import sqlite3

    db_file = tmp_path / "vacuum.db"

    # Daten einfügen und wieder löschen → Freiraum in der DB-Datei
    con = sqlite3.connect(db_file)
    for sub in ("u1", "u2", "u3"):
        con.execute(
            "INSERT INTO user (sub, kind, created_at) VALUES (?, 'oidc', ?)",
            (sub, "2026-01-01T00:00:00+00:00"),
        )
    con.execute("DELETE FROM user WHERE sub IN ('u1','u2')")
    con.commit()
    con.close()

    resp = client.post("/api/admin/vacuum")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["before_bytes"] >= 0
    assert body["after_bytes"] >= 0
    assert body["freed_bytes"] >= 0
    # DB-Datei bleibt intakt
    assert Path(db_file).stat().st_size > 0


def test_vacuum_ohne_admin_403(client):
    from app.deps import require_admin
    from app.main import app

    # Admin-Override entfernen → echter require_admin (Session leer) → 403
    app.dependency_overrides.pop(require_admin, None)
    resp = client.post("/api/admin/vacuum")
    assert resp.status_code == 403


def test_vacuum_oidc_aus_403(tmp_path, monkeypatch):
    """OIDC_ENABLED=False → Admin-Bereich komplett deaktiviert."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    db_file = tmp_path / "vacuum2.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        resp = c.post("/api/admin/vacuum")
    assert resp.status_code == 403
