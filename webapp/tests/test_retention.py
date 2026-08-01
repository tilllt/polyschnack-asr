"""Retention-Sweep (Task B4) — 15 min nach letzter Aktivität wird alles gelöscht."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Recording, RecordingShare, TranscriptVersion, User
from app.retention import sweep


def _old():
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    return eng


def test_sweep_deletes_inactive_anon_user(tmp_path):
    eng = _engine(tmp_path)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"X")
    with Session(eng) as s:
        u = User(id=1, sub="anon:1", kind="anonymous", display_name="Funny Fox",
                 last_seen_at=_old())
        s.add(u)
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1))
        s.add(RecordingShare(rec_id=1, user_id=2, level="read"))
        s.add(TranscriptVersion(rec_id=1, version_no=1, kind="transcribe", text="X"))
        s.commit()
    with Session(eng) as s:
        assert sweep(s) == 1
        assert s.get(User, 1) is None
        assert s.get(Recording, 1) is None
    assert not audio.exists()


def test_sweep_keeps_active_anon_user(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(User(id=1, sub="anon:2", kind="anonymous", display_name="Brave Owl",
                   last_seen_at=_now()))
        s.commit()
    with Session(eng) as s:
        assert sweep(s) == 0
        assert s.get(User, 1) is not None


def test_sweep_keeps_oidc_users(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(User(id=1, sub="oidc-sub", kind="oidc", last_seen_at=_old()))
        s.commit()
    with Session(eng) as s:
        assert sweep(s) == 0
        assert s.get(User, 1) is not None


def test_sweep_keeps_anon_without_last_seen(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(User(id=1, sub="anon:3", kind="anonymous", display_name="Lucky Llama"))
        s.commit()
    with Session(eng) as s:
        assert sweep(s) == 0
        assert s.get(User, 1) is not None
