"""Queue-Manager-Tests (Task 6) — Worker + crud gemockt, keine echte DB nötig."""
from __future__ import annotations

import threading
import time

import pytest

from app import queue as queue_mod
from app.queue import QueueError, QueueFullError, QueueManager


class _FakeCrud:
    """Stand-in for app.crud inside the queue module (DB-frei)."""

    def __init__(self):
        self.queued: list = []
        self.processing: list = []

    def set_queued(self, session, rec_id, backend):
        self.queued.append((rec_id, backend))

    def set_processing(self, session, rec_id):
        self.processing.append(rec_id)

    def get_recording(self, session, rec_id):
        return None

    def avg_recent_processing_ms(self, session, limit=20):
        return 0.0


def _make_manager(monkeypatch, *, start: bool):
    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    m = QueueManager(max_queue_len=3)
    if start:
        m.start()
    return m


@pytest.fixture()
def qm(monkeypatch):
    m = _make_manager(monkeypatch, start=True)
    yield m
    m.stop()


@pytest.fixture()
def qm_no_worker(monkeypatch):
    """QueueManager OHNE Worker — für reine Queue-Logik-Tests (kein Race).

    Wichtig: enqueue() ruft _ensure_workers() auf und startet damit IMMER
    Worker (auch ohne start()). Wenn available_services() Services liefert
    (CI-Env), verarbeiten die Jobs sofort -> position()==0. Deshalb hier
    _ensure_workers deaktivieren.
    """
    m = _make_manager(monkeypatch, start=False)
    monkeypatch.setattr(m, "_ensure_workers", lambda: None)
    return m


def test_enqueue_returns_position_one(qm):
    assert qm.enqueue(1, None, "ps-pk-onnx") == 1
    assert qm.queued_count() == 1


def test_duplicate_enqueue_raises(qm):
    qm.enqueue(1, None, "ps-pk-onnx")
    with pytest.raises(QueueError):
        qm.enqueue(1, None, "ps-pk-onnx")


def test_queue_full_raises(qm, monkeypatch):
    # Worker blockieren → Jobs bleiben in der Queue (deterministisch, kein Race)
    def slow_process(rec_id, backend=None):
        time.sleep(5)

    monkeypatch.setattr(queue_mod, "process_recording", slow_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    qm.enqueue(2, None, "ps-pk-onnx")
    qm.enqueue(3, None, "ps-pk-onnx")
    with pytest.raises(QueueFullError):
        qm.enqueue(4, None, "ps-pk-onnx")


def test_position_counts_same_backend_only(qm_no_worker):
    # Ohne Worker: position() ist reine Queue-Logik. Mit Worker setzt der
    # Worker den Job sofort auf 'processing' -> position 0 (CI-Timing-Race).
    qm_no_worker.enqueue(1, None, "ps-pk-onnx")
    qm_no_worker.enqueue(2, None, "crispr-pk-cpp")
    qm_no_worker.enqueue(3, None, "ps-pk-onnx")
    assert qm_no_worker.position(1) == 1
    assert qm_no_worker.position(2) == 1  # anderer Endpunkt, andere Reihe
    assert qm_no_worker.position(3) == 2


def test_active_jobs_for(qm, monkeypatch):
    # Worker blockieren → Jobs bleiben in der Queue (deterministisch)
    def slow_process(rec_id, backend=None):
        time.sleep(5)

    monkeypatch.setattr(queue_mod, "process_recording", slow_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    qm.enqueue(2, None, "crispr-pk-cpp")
    assert qm.active_jobs_for("ps-pk-onnx") == 1
    assert qm.active_jobs_for("crispr-pk-cpp") == 1
    assert qm.active_jobs_for("crispr-qwen3") == 0


def test_worker_processes_jobs_with_bound_backend(qm, monkeypatch):
    """Jeder Job läuft mit SEINEM Backend (get_client-Aufruf mit backend)."""
    seen: list = []

    def fake_process(rec_id, backend=None):
        seen.append((rec_id, backend))

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    qm.enqueue(2, None, "crispr-qwen3")
    deadline = time.time() + 5
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert sorted(seen) == [(1, "ps-pk-onnx"), (2, "crispr-qwen3")]
    assert qm.queued_count() == 0  # Jobs nach Abschluss entfernt


def test_worker_respects_endpoint_capacity(qm, monkeypatch):
    """Concurrency 1 pro Endpunkt: nie zwei Jobs desselben Backends parallel."""
    started = threading.Event()
    release = threading.Event()
    concurrent = []
    lock = threading.Lock()

    def slow_process(rec_id, backend=None):
        with lock:
            concurrent.append(rec_id)
            n = len(concurrent)
        started.set()
        assert n == 1, f"parallel jobs on same endpoint: {concurrent}"
        release.wait(timeout=5)
        with lock:
            concurrent.remove(rec_id)

    monkeypatch.setattr(queue_mod, "process_recording", slow_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    qm.enqueue(2, None, "ps-pk-onnx")
    assert started.wait(timeout=5)
    time.sleep(0.2)
    release.set()
    deadline = time.time() + 5
    while qm.queued_count() > 0 and time.time() < deadline:
        time.sleep(0.02)


def test_cancel_queued_job(qm, monkeypatch):
    done = threading.Event()

    def fake_process(rec_id, backend=None):
        done.wait(timeout=5)  # Job bleibt processing, bis done gesetzt wird

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    qm.enqueue(1, 7, "ps-pk-onnx")
    qm.enqueue(2, 42, "ps-pk-onnx")  # wartet auf Endpunkt

    assert qm.cancel(2, user_id=99) is False  # fremder User -> abgelehnt
    assert qm.cancel(2, user_id=42) is True   # Eigentümer -> gelöscht
    qm.enqueue(3, 43, "ps-pk-onnx")
    assert qm.cancel(3, user_id=None, is_admin=True) is True  # Admin -> gelöscht
    done.set()
    deadline = time.time() + 5
    while qm.queued_count() > 0 and time.time() < deadline:
        time.sleep(0.02)


def test_cancel_processing_not_allowed(qm, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_process(rec_id, backend=None):
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    assert started.wait(timeout=5)
    assert qm.cancel(1, user_id=None) is False  # processing ist nicht abbrechbar
    release.set()
    deadline = time.time() + 5
    while qm.queued_count() > 0 and time.time() < deadline:
        time.sleep(0.02)
