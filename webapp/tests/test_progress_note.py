"""progress_note: Diarization-Phase wird dem Frontend als Hinweis gemeldet.

Change 011 (2026-08-17): zusätzlich Heartbeat (last_heartbeat_at),
Phasenwechsel (phase_started_at) und Queue-Felder in der Serialisierung.
"""
from __future__ import annotations

import time

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.crud import set_progress


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/pnote.db")
    SQLModel.metadata.create_all(eng)
    return eng


def _mk(db):
    from app.models import Recording

    with Session(db) as s:
        rec = Recording(
            uid="pnote-1", original_name="a.wav", mime="audio/wav",
            stored_path="/tmp/a.wav", size_bytes=100,
            status="processing", progress_pct=50,
        )
        s.add(rec)
        s.commit()
        return rec.id


def test_set_progress_sets_note(db):
    """set_progress mit note setzt progress_pct UND progress_note."""
    from app.models import Recording

    rec_id = _mk(db)

    with Session(db) as s:
        set_progress(s, rec_id, 96, note="diarization")
        rec = s.get(Recording, rec_id)
        assert rec.progress_pct == 96
        assert rec.progress_note == "diarization"

    # ohne note wird nur pct gesetzt — die Note bleibt bestehen
    with Session(db) as s:
        set_progress(s, rec_id, 97)
        rec = s.get(Recording, rec_id)
        assert rec.progress_pct == 97
        assert rec.progress_note == "diarization"


def test_progress_note_field_in_model(db):
    """Die neue Spalte ist im Schema (Auto-Migration nutzt das Model)."""
    from sqlalchemy import inspect

    cols = {c["name"] for c in inspect(db).get_columns("recording")}
    assert "progress_note" in cols


# ---------------------------------------------------------------- Change 011


def test_set_progress_ticks_heartbeat(db):
    """Jeder set_progress-Aufruf aktualisiert last_heartbeat_at (Change 011)."""
    from app.models import Recording

    rec_id = _mk(db)

    with Session(db) as s:
        set_progress(s, rec_id, 21, note="asr")
        rec = s.get(Recording, rec_id)
        assert rec.last_heartbeat_at is not None
        first = rec.last_heartbeat_at

    time.sleep(0.02)  # sicherstellen, dass der Timestamp sich bewegt

    with Session(db) as s:
        set_progress(s, rec_id, 21, note="asr")
        rec = s.get(Recording, rec_id)
        assert rec.last_heartbeat_at >= first


def test_phase_change_sets_phase_started_at(db):
    """Neue Note setzt phase_started_at; gleiche Note lässt es stehen."""
    from app.models import Recording

    rec_id = _mk(db)

    with Session(db) as s:
        set_progress(s, rec_id, 20, note="asr")
        rec = s.get(Recording, rec_id)
        assert rec.phase_started_at is not None
        phase_start = rec.phase_started_at

    time.sleep(0.02)

    # gleiche Note → phase_started_at bleibt unverändert
    with Session(db) as s:
        set_progress(s, rec_id, 21, note="asr")
        rec = s.get(Recording, rec_id)
        assert rec.phase_started_at == phase_start

    # neue Note → phase_started_at springt auf jetzt
    time.sleep(0.02)
    with Session(db) as s:
        set_progress(s, rec_id, 96, note="diarization")
        rec = s.get(Recording, rec_id)
        assert rec.phase_started_at > phase_start
        assert rec.progress_note == "diarization"


def test_heartbeat_fields_in_schema(db):
    """Die Change-011-Spalten existieren im Schema (Auto-Migration)."""
    from sqlalchemy import inspect

    cols = {c["name"] for c in inspect(db).get_columns("recording")}
    assert "phase_started_at" in cols
    assert "last_heartbeat_at" in cols


def test_serialization_includes_heartbeat_and_queue_fields(db):
    """_recording_to_dict liefert Heartbeat- und Queue-Felder (Change 011)."""
    from app.models import Recording
    from app.routers.recordings import _recording_to_dict

    rec_id = _mk(db)

    with Session(db) as s:
        set_progress(s, rec_id, 21, note="asr")
        rec = s.get(Recording, rec_id)
        d = _recording_to_dict(rec)
        assert d["progress_pct"] == 21
        assert d["progress_note"] == "asr"
        assert d["phase_started_at"] is not None
        assert d["last_heartbeat_at"] is not None
        # status ist "processing" (kein Queue-Job) → Queue-Felder None
        assert d["queue_position"] is None
        assert d["queue_eta_s"] is None
        assert d["queue_backend"] is None
