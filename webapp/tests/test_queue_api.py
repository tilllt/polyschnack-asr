"""Queue-API-Tests (Task 7) — Router-Funktionen direkt, Queue gemockt."""
from __future__ import annotations

import time

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
def qm(monkeypatch, tmp_path):
    """Frischer QueueManager mit gemocktem crud + tmp-SQLite.

    Change 155 (Schritt 2): die Job-Tabelle wird in eine tmp-DB gelegt
    (db.engine zur Laufzeit gemockt) — die Persistenz läuft echt, ohne
    die Dev-DB anzufassen.
    """
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(
        f"sqlite:///{tmp_path / 'qapi.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.db.engine", eng)

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
    # CI-Flake 2026-08-21 (Pipeline 4254): Der echte process_recording
    # schlägt mit gemocktem crud (get_recording → None) sofort fehl, der
    # Worker entfernt den Job aus _jobs, und cancel() 404t ("not
    # cancellable") — ein Race, der unter CI-Last mal verliert. Langsamer
    # No-Op hält den Job deterministisch in der Queue (queued oder
    # processing → cancel() gibt in beiden Fällen True zurück).
    monkeypatch.setattr(queue_mod, "process_recording",
                        lambda rec_id, backend=None, job=None: time.sleep(5))
    m = QueueManager(max_queue_len=5)
    # Change 155 (Schritt 2): OHNE Worker — die Positionen sollen
    # deterministisch queued bleiben (ein echter Worker setzt Jobs sofort
    # auf processing → position()==0; Race unter SQLite-Write-Locks).
    monkeypatch.setattr(m, "_ensure_workers", lambda: None)
    m.start()
    monkeypatch.setattr(queue_api, "queue_manager", m)
    yield m
    m.stop()


def _patch_user(monkeypatch, uid, is_admin=False):
    monkeypatch.setattr(queue_api, "_current_user", lambda request, session=None: uid)
    monkeypatch.setattr(queue_api, "_is_admin", lambda request: is_admin)


def test_list_queue_anonymises_foreign_jobs(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 7, "ps-pk-onnx")   # eigene
    qm.enqueue(2, 99, "ps-pk-onnx")  # fremde (User 99)

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
    qm.enqueue(1, 7, "ps-pk-onnx")
    qm.enqueue(2, 99, "ps-pk-onnx")
    data = queue_api.list_queue(_FakeRequest(session={"is_admin": True}))
    assert all(j["is_mine"] for j in data["jobs"])


def test_list_queue_reports_total_concurrency(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    data = queue_api.list_queue(_FakeRequest(session={}))
    assert data["concurrency"] >= 1


def test_cancel_own_queued_job(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 7, "ps-pk-onnx")
    assert queue_api.cancel_queue_job(1, _FakeRequest(session={})) == {"cancelled": 1}


def test_cancel_foreign_job_404(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    qm.enqueue(1, 99, "ps-pk-onnx")
    with pytest.raises(HTTPException) as ei:
        queue_api.cancel_queue_job(1, _FakeRequest(session={}))
    assert ei.value.status_code == 404


def test_cancel_unknown_job_404(qm, monkeypatch):
    _patch_user(monkeypatch, uid=7)
    with pytest.raises(HTTPException) as ei:
        queue_api.cancel_queue_job(4711, _FakeRequest(session={}))
    assert ei.value.status_code == 404
