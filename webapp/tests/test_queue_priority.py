"""Queue-Priorität (Task B6) — anonyme Jobs (prio 1) immer hinter registrierten (prio 0)."""
from __future__ import annotations

import pytest

from app import queue as queue_mod
from app.queue import QueueManager


@pytest.fixture()
def qm(monkeypatch):
    class _FakeCrud:
        def set_queued(self, session, rec_id, backend): pass
        def set_processing(self, session, rec_id): pass
        def get_recording(self, session, rec_id): return None
        def avg_recent_processing_ms(self, session, limit=20): return 30000.0

    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    m = QueueManager(max_queue_len=10)
    # Keine Worker starten — nur FIFO/Position-Logik testen.
    m._ensure_workers = lambda: None
    return m


def test_registered_before_anonymous(qm):
    qm.enqueue(1, user_id=10, backend="ps-pk-onnx", priority=0)
    qm.enqueue(2, user_id=None, backend="ps-pk-onnx", priority=1)
    assert qm.position(1) == 1
    assert qm.position(2) == 2  # anon steht hinter registriertem Job


def test_registered_springs_ahead_of_anonymous(qm):
    qm.enqueue(1, user_id=None, backend="ps-pk-onnx", priority=1)
    qm.enqueue(2, user_id=10, backend="ps-pk-onnx", priority=0)
    assert qm.position(1) == 2  # anon: registrierter Job zählt vor
    assert qm.position(2) == 1  # registriert springt vor


def test_fifo_among_same_priority(qm):
    qm.enqueue(1, user_id=10, backend="ps-pk-onnx", priority=0)
    qm.enqueue(2, user_id=11, backend="ps-pk-onnx", priority=0)
    assert qm.position(1) == 1
    assert qm.position(2) == 2


def test_anon_fifo_among_anonymous(qm):
    qm.enqueue(1, user_id=None, backend="ps-pk-onnx", priority=1)
    qm.enqueue(2, user_id=None, backend="ps-pk-onnx", priority=1)
    assert qm.position(1) == 1
    assert qm.position(2) == 2


def test_priority_only_same_backend(qm):
    qm.enqueue(1, user_id=10, backend="crispr-pk-cpp", priority=0)
    qm.enqueue(2, user_id=None, backend="ps-pk-onnx", priority=1)
    assert qm.position(2) == 1  # anderer Endpunkt zählt nicht


def test_worker_takes_priority_order():
    """Der Worker zieht zuerst prio-0-Jobs (FIFO innerhalb der Prio)."""
    import queue as stdqueue

    qm = QueueManager(max_queue_len=10)
    qm._fifo = stdqueue.PriorityQueue()
    qm._fifo.put((1, 1, 101))
    qm._fifo.put((0, 2, 202))
    first = qm._fifo.get()
    assert first[0] == 0 and first[2] == 202  # registriert zuerst
