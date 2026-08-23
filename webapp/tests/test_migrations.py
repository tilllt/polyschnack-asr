"""Migrations-Tests — Change 103: 094-DB (transcriptionrun ohne
Settings-Spalten) migriert ohne Crash (Produktions-Startup-Fail)."""
from __future__ import annotations

import pytest
from sqlalchemy import text as sa_text
from sqlmodel import SQLModel, Session, create_engine


def _build_094_db(path: str) -> None:
    """Erzeugt eine DB im Change-094-Zustand: recording MIT Alt-Spalten,
    transcriptionrun OHNE Settings-Spalten."""
    eng = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.exec(sa_text("DROP TABLE transcriptionrun"))
        s.exec(sa_text("""CREATE TABLE transcriptionrun (
            id INTEGER NOT NULL PRIMARY KEY,
            rec_id INTEGER NOT NULL,
            backend VARCHAR NOT NULL DEFAULT '',
            language VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'queued',
            created_by_user_id INTEGER,
            created_at DATETIME NOT NULL)"""))
        # Alt-Spalten der recording-Tabelle (099-Modell hat sie nicht mehr)
        for col in (
            "enable_vad BOOLEAN NOT NULL DEFAULT 0",
            "enable_diarize BOOLEAN NOT NULL DEFAULT 0",
            "enable_streaming BOOLEAN NOT NULL DEFAULT 0",
            "enable_noise_reduce BOOLEAN NOT NULL DEFAULT 1",
            "enable_punctuation BOOLEAN NOT NULL DEFAULT 0",
            "enable_llm_enhance BOOLEAN NOT NULL DEFAULT 0",
        ):
            s.exec(sa_text(f"ALTER TABLE recording ADD COLUMN {col}"))
        for col in (
            "diarize_num_speakers INTEGER",
            "diarize_min_duration_off FLOAT",
            "diarize_method VARCHAR",
            "enable_enhance VARCHAR NOT NULL DEFAULT 'off'",
            "prompt_template_id INTEGER",
            "delivery_target_id INTEGER",
            "llm_endpoint_id INTEGER",
        ):
            s.exec(sa_text(f"ALTER TABLE recording ADD COLUMN {col}"))
        s.exec(sa_text("""INSERT INTO recording
            (id, uid, original_name, stored_path, mime, size_bytes, status,
             backend, segments_manual, alignment, diar_status, progress_pct,
             created_at, updated_at, share_token, text, enable_vad)
            VALUES (1, 'u1', 'a.mp3', '/x/a.mp3', 'audio/mpeg', 10, 'done',
                    'ps-pk-onnx', 0, 'none', 'none', 100,
                    '2026-08-01', '2026-08-01', 't', 'Hallo Welt', 1)"""))
        s.commit()
    eng.dispose()


def test_migration_094_db_ohne_run_settings_columns(tmp_path):
    """Change 103: Der 099-Backfill crasht NICHT mehr mit
    'no such column: enable_vad' (Produktions-Befund 2026-08-23)."""
    from app.db import _drop_legacy_settings_columns

    db_path = tmp_path / "mig094.db"
    _build_094_db(str(db_path))
    eng = create_engine(f"sqlite:///{db_path}")

    with Session(eng) as s:
        _drop_legacy_settings_columns(s)  # darf nicht werfen

    with Session(eng) as s:
        # Baseline-Run entstand mit den Settings aus den Alt-Spalten
        runs = s.exec(sa_text(
            "SELECT rec_id, enable_vad, status FROM transcriptionrun")).all()
        assert len(runs) == 1
        assert runs[0][1] == 1  # enable_vad aus recording übernommen
        assert runs[0][2] == "done"  # Text vorhanden
        # Settings-Spalten sind aus recording entfernt
        rcols = [r[1] for r in s.exec(
            sa_text("PRAGMA table_info(recording)")).all()]
        assert "enable_vad" not in rcols
        assert "enable_enhance" not in rcols
        # transcriptionrun hat die Settings-Spalten jetzt
        tcols = [r[1] for r in s.exec(
            sa_text("PRAGMA table_info(transcriptionrun)")).all()]
        assert "enable_vad" in tcols
        assert "delivery_target_id" in tcols

    # Idempotenz: zweiter Lauf — kein Crash, keine Doppel-Runs
    with Session(eng) as s:
        _drop_legacy_settings_columns(s)
    with Session(eng) as s:
        n = s.exec(sa_text(
            "SELECT COUNT(*) FROM transcriptionrun")).one()[0]
        assert n == 1
    eng.dispose()


def test_migration_bereits_migrierte_db_bleibt_unberuehrt(tmp_path):
    """Voll-migrierte DB (Spalten weg): Migration ist ein No-op."""
    from app.db import _drop_legacy_settings_columns

    db_path = tmp_path / "mig_done.db"
    _build_094_db(str(db_path))
    eng = create_engine(f"sqlite:///{db_path}")
    with Session(eng) as s:
        _drop_legacy_settings_columns(s)
    # Zweite DB: frisch mit AKTUELLEM Modell (schon 099)
    db2 = tmp_path / "mig_done2.db"
    eng2 = create_engine(f"sqlite:///{db2}")
    SQLModel.metadata.create_all(eng2)
    with Session(eng2) as s:
        _drop_legacy_settings_columns(s)  # drop leer → return, kein Crash
    eng.dispose()
    eng2.dispose()
