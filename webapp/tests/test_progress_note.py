"""progress_note: Diarization-Phase wird dem Frontend als Hinweis gemeldet."""
from __future__ import annotations

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
