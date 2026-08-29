"""Change 156: ehrliche Statusableitung — Reconcile + Phase im Payload.

Der Job (jobs-Tabelle) ist die Wahrheit: ein `rec.status` OHNE aktiven Job
ist eine Pseudo-Info (Spinner ohne Prozess, z.B. nach Stack-Restarts);
ein laufender Align/Diarize-Job muss auf der Karte als Phase erscheinen.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import db as db_module
from app.models import Job, Recording


@pytest.fixture()
def db(tmp_path, monkeypatch):
    eng = create_engine(
        f"sqlite:///{tmp_path}/status.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


def test_reconcile_stale_processing(db):
    """status=processing ohne aktiven Job → done (Text vorhanden) bzw.
    failed (kein Text); mit aktivem Job bleibt processing."""
    from app.routers.recordings import _reconcile_stale_statuses

    with Session(db) as s:
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="x",
                        status="processing"))
        s.add(Recording(id=2, uid="r2", original_name="b.mp3", stored_path="x",
                        status="processing", text="fertig"))
        s.add(Recording(id=3, uid="r3", original_name="c.mp3", stored_path="x",
                        status="processing", text="läuft"))
        s.add(Job(id=1, key="3", rec_id=3, kind="align", status="running"))
        s.commit()

    with Session(db) as s:
        _reconcile_stale_statuses(s)

    with Session(db) as s:
        assert s.get(Recording, 1).status == "failed"        # kein Text, kein Job
        assert s.get(Recording, 2).status == "done"          # Text vorhanden
        assert s.get(Recording, 3).status == "processing"    # aktiver Job!


def test_active_job_phase_in_payload(db):
    """Laufender Align-Job → Karte meldet status=processing + phase=align
    (vorher zeigte sie nur den fertigen Transkriptions-Status)."""
    from app.routers.recordings import _recording_to_dict

    with Session(db) as s:
        s.add(Recording(id=4, uid="r4", original_name="d.mp3", stored_path="x",
                        status="done", text="fertig", duration_s=100.0))
        s.add(Job(id=2, key="4", rec_id=4, kind="align",
                  backend="crispr-align", status="running"))
        s.commit()

    with Session(db) as s:
        d = _recording_to_dict(s.get(Recording, 4), session=s)
        assert d["status"] == "processing"
        assert d["phase"] == "align"


def test_no_active_job_no_phase(db):
    """Ohne aktiven Job bleibt der echte Status (done) + phase=None."""
    from app.routers.recordings import _recording_to_dict

    with Session(db) as s:
        s.add(Recording(id=5, uid="r5", original_name="e.mp3", stored_path="x",
                        status="done", text="fertig", duration_s=50.0))
        s.commit()

    with Session(db) as s:
        d = _recording_to_dict(s.get(Recording, 5), session=s)
        assert d["status"] == "done"
        assert d["phase"] is None
