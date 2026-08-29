"""Job-Cancel: queued + processing (Cancel-Flag, Job-Timeout, Queue-Freiheit)."""
from __future__ import annotations

import threading
import time

import pytest

from app.queue import Job, QueueManager


class _FakeJob:
    """Minimaler Job-Stand-in mit den von service genutzten Attributen."""

    def __init__(self, max_s: float = 3600.0, cancel: bool = False):
        self.cancel_requested = cancel
        self._max_processing_s = max_s
        self.started_at = time.time()

    @property
    def running_s(self) -> float:
        return time.time() - self.started_at


def test_cancel_processing_setzt_flag():
    qm = QueueManager(max_queue_len=5)
    # Job direkt in die Registry legen (processing)
    job = Job(rec_id=7, user_id=1, backend="ps-pk-onnx", status="processing")
    qm._jobs[7] = job
    assert qm.cancel(7, user_id=1) is True
    assert job.cancel_requested is True


def test_cancel_processing_falscher_user():
    qm = QueueManager(max_queue_len=5)
    job = Job(rec_id=7, user_id=1, backend="ps-pk-onnx", status="processing")
    qm._jobs[7] = job
    assert qm.cancel(7, user_id=2) is False
    assert job.cancel_requested is False


def test_cancel_processing_admin_darf_fremde():
    qm = QueueManager(max_queue_len=5)
    job = Job(rec_id=7, user_id=1, backend="ps-pk-onnx", status="processing")
    qm._jobs[7] = job
    assert qm.cancel(7, user_id=2, is_admin=True) is True


def test_cancel_queued_entfernt_und_reset(tmp_path, monkeypatch):
    qm = QueueManager(max_queue_len=5)
    # Ohne DB-Zugriff: nur Registry-Verhalten prüfen
    job = Job(rec_id=7, user_id=1, backend="ps-pk-onnx", status="queued")
    qm._jobs[7] = job
    from sqlmodel import create_engine

    # Change 099-Review: Der DB-Reset hängt an der app-Engine — im
    # Einzellauf zeigt sie auf eine echte DB (der Reset klappt). Für den
    # Unit-Test: Engine auf einen nicht existierenden Pfad, damit der
    # Reset deterministisch scheitert (Flag-Entfernen passiert davor).
    # Change 155 (Schritt 2): der Row-Update (cancelled) ist defensiv, aber
    # der Recording-Reset bleibt bewusst nicht-defensiv — ein DB-Fehler
    # beim Cancel muss sichtbar sein. Flag-Entfernen passiert davor.
    monkeypatch.setattr(
        "app.db.engine",
        create_engine("sqlite:////nonexistent-yjs/queue.db"),
    )
    with pytest.raises(Exception):
        # DB-Session fehlt (Engine ungültig) — der Reset schlägt fehl, aber das
        # Flag-Entfernen passiert VOR dem DB-Zugriff.
        qm.cancel(7, user_id=1)
    # Der Job wurde aus der Registry entfernt (vor dem DB-Reset)
    assert 7 not in qm._jobs


def test_cancel_unbekannt_false():
    qm = QueueManager(max_queue_len=5)
    assert qm.cancel(999, user_id=1) is False


# ---------------------------------------------------------------------------
# Job-Timeout: _cancelled() aus service prüfen
# ---------------------------------------------------------------------------

def test_cancelled_wegen_cancel_flag():
    from app.service import _cancelled

    job = _FakeJob(cancel=True)
    assert _cancelled(job, 1) is True


def test_cancelled_wegen_timeout():
    from app.service import _cancelled

    job = _FakeJob(max_s=0.05)  # 50 ms
    time.sleep(0.1)
    assert _cancelled(job, 1) is True


def test_cancelled_normal_laeuft():
    from app.service import _cancelled

    job = _FakeJob(max_s=3600.0)
    assert _cancelled(job, 1) is False


def test_cancelled_ohne_job_false():
    from app.service import _cancelled

    assert _cancelled(None, 1) is False


# ---------------------------------------------------------------------------
# Job.running_s
# ---------------------------------------------------------------------------

def test_running_s_waachst():
    job = Job(rec_id=1, user_id=1, backend="x")
    job.started_at = time.time() - 2.0
    assert job.running_s >= 2.0


def test_running_s_ohne_start_0():
    job = Job(rec_id=1, user_id=1, backend="x")
    assert job.running_s == 0.0
