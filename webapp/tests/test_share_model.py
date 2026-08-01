"""Tests für das RecordingShare-Modell (Task A2)."""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import RecordingShare


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    return eng


def test_share_model_roundtrip(engine):
    with Session(engine) as s:
        sh = RecordingShare(rec_id=1, user_id=2, level="write")
        s.add(sh)
        s.commit()
        s.refresh(sh)
        assert sh.id is not None
        assert sh.level == "write"
        assert sh.created_at is not None


def test_duplicate_pair_rejected(engine):
    with Session(engine) as s:
        s.add(RecordingShare(rec_id=1, user_id=2, level="read"))
        s.commit()
    with Session(engine) as s, pytest.raises(Exception):
        s.add(RecordingShare(rec_id=1, user_id=2, level="full"))
        s.commit()


def test_distinct_pairs_allowed(engine):
    with Session(engine) as s:
        s.add(RecordingShare(rec_id=1, user_id=2, level="read"))
        s.add(RecordingShare(rec_id=1, user_id=3, level="write"))
        s.commit()
        assert len(s.exec(__import__("sqlmodel").select(RecordingShare)).all()) == 2
