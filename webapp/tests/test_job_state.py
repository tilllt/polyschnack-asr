"""Change 183 — Job-Zustandsmaschine: job_transition/job_cancelled."""

import pytest

from app.job_state import job_cancelled, job_request_cancel, job_transition
from app.models import Job


def _setup(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


def _mkjob(eng):
    from sqlmodel import Session

    with Session(eng) as s:
        j = Job(key="align-1", rec_id=1, kind="align", status="queued")
        s.add(j)
        s.commit()
        s.refresh(j)
        return j.id


def test_transition_setzt_zeiten_und_phase(tmp_path, monkeypatch):
    from sqlmodel import Session

    eng = _setup(tmp_path, monkeypatch)
    rid = _mkjob(eng)
    with Session(eng) as s:
        job_transition(s, rid, status="running")
        job_transition(s, rid, phase="alignment", pct=0)
    with Session(eng) as s:
        row = s.get(Job, rid)
        assert row.status == "running"
        assert row.phase == "alignment"
        assert row.pct == 0
        assert row.started_at is not None
        assert row.phase_started_at is not None
        assert row.heartbeat_at is not None
        # Change 184 (Regression, Live-Befund 03.09.): phase_started_at/
        # heartbeat_at waren als str deklariert — der DB-Read lieferte str
        # statt datetime → iso_utc() → AttributeError → 500 auf
        # /api/recordings, sobald ein Job lief. `is not None` blieb für str
        # grün; der Typ ist der eigentliche Vertrag (wie started_at).
        import datetime as _dt

        assert isinstance(row.started_at, _dt.datetime)
        assert isinstance(row.phase_started_at, _dt.datetime)
        assert isinstance(row.heartbeat_at, _dt.datetime)


def test_terminal_raeumt_heartbeat_und_setzt_finished(tmp_path, monkeypatch):
    from sqlmodel import Session

    eng = _setup(tmp_path, monkeypatch)
    rid = _mkjob(eng)
    with Session(eng) as s:
        job_transition(s, rid, status="running")
        job_transition(s, rid, status="failed", error="kaputt")
    with Session(eng) as s:
        row = s.get(Job, rid)
        assert row.status == "failed"
        assert row.error == "kaputt"
        assert row.heartbeat_at is None  # kein Heartbeat nach dem Ende
        assert row.finished_at is not None


def test_cancel_persistent(tmp_path, monkeypatch):
    from sqlmodel import Session

    eng = _setup(tmp_path, monkeypatch)
    rid = _mkjob(eng)
    with Session(eng) as s:
        assert not job_cancelled(s, rid)
        assert job_request_cancel(s, rid)
    with Session(eng) as s:  # neue Session = "Restart" — Flag überlebt
        assert job_cancelled(s, rid)
