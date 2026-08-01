"""Queue-API-Tests (Task 7) — Router-Funktionen direkt, Queue gemockt."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import queue as queue_mod
from app.queue import QueueManager
from app.routers import queue_api


class _FakeRequest:
    def __init__(self, session=None, oidc_enabled=True):
        self.session = session or {}
        self._oidc = oidc_enabled


@pytest.fixture()
def qm(monkeypatch):
    """Frischer QueueManager mit gemocktem crud (keine echte DB)."""
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
    m = QueueManager(max_queue_len=5)
    m.start()
    monkeypatch.setattr(queue_api, "queue_manager", m)
    yield m
    m.stop()


def _patch_user(monkeypatch, uid, is_admin=False):
    monkeypatch.setattr(queue_api, "_current_user", lambda request: uid)
    monkeypatch.setattr(queue_api, "_is_admin", lambda request: is_admin)


def test_list_queue_anonymises_foreign_jobs(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 7, "pk-python")   # eigene
    qm.enqueue(2, 99, "pk-python")  # fremde (User 99)

    data = queue_api.list_queue(_FakeRequest(session={}))
    jobs = {j["job_id"]: j for j in data["jobs"]}
    assert jobs[1]["is_mine"] is True
    assert jobs[2]["is_mine"] is False
    # Fremde Jobs tragen keine Namen/User-IDs
    for j in jobs.values():
        assert "original_name" not in j and "user_id" not in j
    # Position + ETA auf dem eigenen Endpunkt
    assert jobs[1]["position"] == 1
    assert jobs[2]["position"] == 2
    assert jobs[2]["eta_s"] == 60  # 2 * 30s Median


def test_list_queue_admin_sees_all_as_mine(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7, is_admin=True)
    qm.enqueue(1, 7, "pk-python")
    qm.enqueue(2, 99, "pk-python")
    data = queue_api.list_queue(_FakeRequest(session={"is_admin": True}))
    assert all(j["is_mine"] for j in data["jobs"])


def test_list_queue_reports_total_concurrency(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    data = queue_api.list_queue(_FakeRequest(session={}))
    assert data["concurrency"] >= 1


def test_cancel_own_queued_job(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 7, "pk-python")
    assert queue_api.cancel_queue_job(1, _FakeRequest(session={})) == {"cancelled": 1}


def test_cancel_foreign_job_404(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 99, "pk-python")
    with pytest.raises(HTTPException) as ei:
        queue_api.cancel_queue_job(1, _FakeRequest(session={}))
    assert ei.value.status_code == 404


def test_cancel_unknown_job_404(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    with pytest.raises(HTTPException) as ei:
        queue_api.cancel_queue_job(4711, _FakeRequest(session={}))
    assert ei.value.status_code == 404
