"""Change 143: Queue-Recovery + enqueue-Fehler-Rollback.

User-Befund 2026-08-28: „Re-Transcribe wird nur zur Queue hinzugefügt und
fängt nicht an". Zwei Wurzeln:
1. Nach einem Webapp-Neustart kennt der In-Memory-QueueManager DB-Jobs mit
   status='queued' nicht mehr → kein Worker startet sie (verwaiste Jobs).
2. Wird der Run committet, BEVOR enqueue() läuft, und enqueue wirft
   (QueueError/QueueFullError), bleibt ein Orphan-Run in der DB.
"""
import pytest

from app.queue import QueueManager
from app.routers.recordings import _abort_queued_run
from app.models import Recording


@pytest.fixture()
def session(tmp_path, monkeypatch):
    """Eigene SQLite-DB pro Test (Muster test_word_timing)."""
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 'qrec.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    # queue.py hat `engine` beim Import eingefroren → dort ebenfalls patchen.
    # Change 155 (Schritt 2): queue.py liest db.engine zur Laufzeit —
    # Mock dort, damit auch der Job-Tabellen-Pfad in die tmp-DB zeigt.
    monkeypatch.setattr("app.db.engine", eng)
    with Session(eng) as s:
        yield s


@pytest.fixture()
def fresh_manager():
    """Frischer Manager (unabhängig vom Modul-Singleton)."""
    return QueueManager()


def _queued_recording(session, uid="rec-recovery-test"):
    rec = Recording(
        uid=uid, original_name="recovery.wav", status="queued",
        backend="pk", stored_path="/tmp/nope.wav", duration_s=1.0,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def test_recover_queued_reloads_db_jobs(session, fresh_manager):
    """DB-Job mit status='queued' wird beim Start wieder in den Manager geladen."""
    rec = _queued_recording(session)
    fresh_manager._recover_queued()
    assert rec.id in fresh_manager._jobs
    assert fresh_manager._jobs[rec.id].status == "queued"
    # FIFO enthält den Job (Worker kann ihn aufnehmen)
    assert not fresh_manager._fifo.empty()


def test_recover_queued_skips_processing(session, fresh_manager):
    """Nur 'queued' wird wieder aufgenommen — 'processing'/'done' nicht.

    Change 155: processing wird NUR übersprungen, solange der letzte
    DB-Write frisch ist (updated_at < 2 min → läuft evtl. noch, kein
    Doppelstart). Dieser Test legt ein frisches Recording an → skip.
    """
    rec_q = _queued_recording(session)
    rec_p = Recording(
        uid="rec-recovery-proc", original_name="p.wav", status="processing",
        backend="pk", stored_path="/tmp/p.wav", duration_s=1.0,
    )
    session.add(rec_p)
    session.commit()
    fresh_manager._recover_queued()
    assert rec_q.id in fresh_manager._jobs
    assert rec_p.id not in fresh_manager._jobs


def test_recover_processing_zombie_mit_altem_updated_at(session, fresh_manager):
    """Change 155: processing-Zombie (updated_at > 2 min alt, Prozess tot
    durch Crash/Deploy) wird wieder aufgenommen und via set_queued
    konsistent gemacht. User-Befund 2026-08-29: Deploy während laufender
    Transkription liess die Recording ewig auf 'processing' hängen.
    """
    import datetime as dt

    from app import crud

    rec = Recording(
        uid="rec-recovery-zombie", original_name="z.wav", status="processing",
        backend="pk", stored_path="/tmp/z.wav", duration_s=1.0,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    # updated_at künstlich altern (1 h zurück)
    rec.updated_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    session.add(rec)
    session.commit()

    fresh_manager._recover_queued()

    assert rec.id in fresh_manager._jobs, "toter processing-Zombie muss wieder aufgenommen werden"
    assert fresh_manager._jobs[rec.id].status == "queued"
    # set_queued hat den DB-Zustand konsistent gemacht (queued statt processing)
    session.refresh(rec)
    assert rec.status == "queued"
    assert not fresh_manager._fifo.empty()


def test_abort_queued_run_rolls_back_pointer(session):
    """Enqueue-Fehler → Run failed + Zeiger auf vorherigen Run zurück."""
    from app.models import TranscriptionRun

    rec = _queued_recording(session)
    old_run_id = rec.current_run_id
    run = TranscriptionRun(rec_id=rec.id, status="queued")
    session.add(run)
    session.flush()  # run.id belegen (Muster Endpunkt Change 099)
    rec.current_run_id = run.id
    _abort_queued_run(session, rec, run, old_run_id)
    assert run.status == "failed"
    assert rec.current_run_id == old_run_id


# --- Change 155 (Schritt 2): Rehydration aus der Job-Tabelle (Pfad A) ---


def test_recover_nimmt_job_row_auf(session, fresh_manager):
    """Job-Row (queued) ist die primäre Rehydrations-Quelle — kind/backend/
    payload kommen exakt aus der Tabelle (kein Recording nötig)."""
    import json

    from app.models import Job

    row = Job(
        key="align-9", rec_id=9, kind="align", backend="ps-pk-onnx",
        priority=0, status="queued",
        payload=json.dumps({"id": "r9", "diar_status": "pending"}),
    )
    session.add(row)
    session.commit()

    fresh_manager._recover_queued()

    assert "align-9" in fresh_manager._jobs
    job = fresh_manager._jobs["align-9"]
    assert job.kind == "align" and job.backend == "ps-pk-onnx"
    assert job.payload == {"id": "r9", "diar_status": "pending"}


def test_recover_skip_frische_running_row(session, fresh_manager):
    """Running-Row mit frischem started_at → läuft evtl. noch → skip."""
    import datetime as dt

    from app.models import Job

    row = Job(
        key="7", rec_id=7, kind="transcribe", backend="pk",
        status="running", started_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(row)
    session.commit()

    fresh_manager._recover_queued()

    assert 7 not in fresh_manager._jobs


def test_recover_nimmt_stale_running_row_auf_mit_attempts(session, fresh_manager):
    """Running-Zombie (started_at alt → Prozess tot) wird wieder aufgenommen,
    attempts wird inkrementiert."""
    import datetime as dt

    from app.models import Job

    row = Job(
        key="7", rec_id=7, kind="transcribe", backend="pk",
        status="running",
        started_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1),
        attempts=1,
    )
    session.add(row)
    session.commit()

    fresh_manager._recover_queued()

    assert 7 in fresh_manager._jobs
    assert fresh_manager._jobs[7].status == "queued"
    session.refresh(row)
    assert row.attempts == 2
