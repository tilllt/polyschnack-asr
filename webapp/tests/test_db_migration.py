"""Regressionstests für die SQLite-Auto-Migration (_auto_migrate).

Hintergrund: Beim Start des Webapp-Containers crashte die App mit
``sqlite3.OperationalError: near "-": syntax error``, sobald eine Bestands-DB
(altes Schema) fehlende Spalten per ``ALTER TABLE ADD COLUMN`` bekam. Ursache:
unquotierte String-Defaults wie ``backend="pk-python"`` erzeugten
``DEFAULT pk-python`` (ungültiges SQL). Diese Tests simulieren eine Bestands-DB
mit Alt-Schema und stellen sicher, dass die Migration fehlerfrei durchläuft.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db as db_module  # noqa: E402


def _create_legacy_schema(db_file: Path) -> None:
    """Erzeugt eine Bestands-DB, deren recording-Tabelle NUR die alten Spalten hat."""
    con = sqlite3.connect(db_file)
    con.executescript(
        """
        CREATE TABLE recording (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP,
            status VARCHAR,
            text TEXT,
            user_id INTEGER
        );
        """
    )
    con.commit()
    con.close()


@pytest.fixture
def legacy_engine(monkeypatch, tmp_path):
    db_file = tmp_path / "legacy.db"
    _create_legacy_schema(db_file)
    eng = create_engine(f"sqlite:///{db_file}")
    # Fehlende Modell-Tabellen anlegen (recording existiert bereits -> bleibt Alt-Schema)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


def test_auto_migrate_legacy_db_ohne_crash(legacy_engine):
    """Migration auf Bestands-DB darf keine SQL-Fehler werfen (Regression)."""
    db_module._auto_migrate()  # darf KEINE Exception auslösen


def test_auto_migrate_fuegt_backend_spalte_mit_default_an(legacy_engine):
    """backend-Spalte (Default 'pk-python') muss korrekt quotiert angelegt werden."""
    db_module._auto_migrate()
    cols = {c["name"] for c in inspect(legacy_engine).get_columns("recording")}
    assert "backend" in cols

    con = sqlite3.connect(str(legacy_engine.url.database))
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recording'"
    ).fetchone()
    con.close()
    # Der generierte DDL muss den Default quotiert enthalten (DEFAULT 'pk-python')
    assert "DEFAULT 'pk-python'" in row[0].lower() or "DEFAULT 'pk-python'" in row[0]


def test_auto_migrate_ist_idempotent(legacy_engine):
    """Zweiter Lauf darf nichts mehr zu tun haben und nicht crashen."""
    db_module._auto_migrate()
    db_module._auto_migrate()  # zweiter Lauf -> kein Fehler
