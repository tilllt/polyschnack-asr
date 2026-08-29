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
def job_db(tmp_path, monkeypatch):
    # Change 155 (Schritt 2): tmp-SQLite für die persistente Job-Tabelle.
    # queue.py liest db.engine zur Laufzeit → dort patchen (crud bleibt
    # gefakt, Service-Verhalten unverändert).
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(
        f"sqlite:///{tmp_path / 'queue_jobs.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.db.engine", eng)  # queue.py liest db.engine zur Laufzeit
    return eng


@pytest.fixture()
def qm(monkeypatch, job_db):
    m = _make_manager(monkeypatch, start=True)
    yield m
    m.stop()


@pytest.fixture()
def qm_no_worker(monkeypatch, job_db):
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

    def fake_process(rec_id, backend=None, job=None):
        seen.append((rec_id, backend))

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    qm.enqueue(2, None, "crispr-qwen3")
    deadline = time.time() + 5
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert sorted(seen) == [(1, "ps-pk-onnx"), (2, "crispr-qwen3")]
    # Change 155 (Schritt 2): der pop passiert NACH dem _finalize_job_row
    # (DB-Read) — deshalb auf das Leeren warten statt sofort zu prüfen.
    deadline = time.time() + 5
    while qm.queued_count() > 0 and time.time() < deadline:
        time.sleep(0.02)
    assert qm.queued_count() == 0  # Jobs nach Abschluss entfernt


def test_worker_respects_endpoint_capacity(qm, monkeypatch):
    """Concurrency 1 pro Endpunkt: nie zwei Jobs desselben Backends parallel."""
    started = threading.Event()
    release = threading.Event()
    concurrent = []
    lock = threading.Lock()

    def slow_process(rec_id, backend=None, job=None):
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


def test_cancel_processing_setzt_flag(qm, monkeypatch):
    # Seit 2026-08-15 (Job-Cancel): processing-Jobs sind ABBRECHBAR —
    # cancel() setzt cancel_requested, der Worker stoppt nach der Phase.
    started = threading.Event()
    release = threading.Event()

    def fake_process(rec_id, backend=None, job=None):
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    qm.enqueue(1, None, "ps-pk-onnx")
    assert started.wait(timeout=5)
    assert qm.cancel(1, user_id=None) is True  # processing → Flag gesetzt
    release.set()
    deadline = time.time() + 5
    while qm.queued_count() > 0 and time.time() < deadline:
        time.sleep(0.02)


# ---------------------------------------------------------------- Change 155


class _FakeSessionCtx:
    """Context-Manager-Session für _recover_queued (DB-frei).

    Change 155 (Schritt 2): Der Recover fragt jetzt die Job-Tabelle
    (JobRow) UND die Recordings ab — die Fake-Session unterscheidet
    nach Modell und liefert die passende Liste (job_rows default leer
    → die Recover-Tests üben den Recording-Fallback-Pfad).
    """

    def __init__(self, rows, job_rows=None):
        self.rows = rows
        self.job_rows = job_rows if job_rows is not None else []
        self._is_job = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def query(self, model):
        self._is_job = getattr(model, "__name__", "") == "Job"
        return self

    def filter(self, *a, **k):
        return self

    def all(self):
        return self.job_rows if self._is_job else self.rows

    def first(self):
        src = self.job_rows if self._is_job else self.rows
        return src[0] if src else None

    def get(self, model, ident):
        return None

    def add(self, obj):
        return None

    def commit(self):
        return None


class _FakeRec:
    def __init__(self, rec_id, status):
        self.id = rec_id
        self.user_id = None
        self.backend = "ps-pk-onnx"
        self.status = status
        self.alignment = ""       # Change 155: kind-Ableitung im Recover
        self.diar_status = ""
        # Change 155: stale updated_at (1 h alt) → sicher tot → re-enqueue
        import datetime as _dt

        self.updated_at = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)


def test_recover_resumes_processing_zombies(monkeypatch):
    """Change 155: processing-Zombies werden beim Start re-enqueued.

    User-Befund 2026-08-29: Deploy während laufender Transkription → die
    Recording klebte ewig auf 'processing' (RAM-Job weg). Beim Start müssen
    queued UND processing-Recordings wieder aufgenommen werden, processing
    zusätzlich via set_queued in einen konsistenten Zustand gebracht.
    """
    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    rows = [_FakeRec(1, "processing"), _FakeRec(2, "queued")]
    monkeypatch.setattr(queue_mod, "Session", lambda engine: _FakeSessionCtx(rows))

    m = QueueManager(max_queue_len=5)
    m._ensure_workers = lambda: None  # type: ignore[assignment] — kein echter Worker
    m.start()

    assert 1 in m._jobs, "processing-Zombie muss wieder aufgenommen werden"
    assert 2 in m._jobs, "queued-Job muss weiterhin aufgenommen werden"
    assert m._jobs[1].status == "queued"
    assert (1, "ps-pk-onnx") in fake.queued, "Zombie muss via set_queued konsistent gemacht werden"
    assert (2, "ps-pk-onnx") not in fake.queued, "queued-Job braucht kein set_queued"


def test_recover_align_und_rediarize_zombies(monkeypatch):
    """Change 155 (Schritt 4): align/rediarize-Zombies (alignment/diar_status)
    werden als eigene Queue-Jobs mit kind + String-Key wieder aufgenommen."""
    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    a = _FakeRec(1, "done")
    a.alignment = "aligning"
    r = _FakeRec(2, "done")
    r.diar_status = "running"
    rows = [a, r]
    monkeypatch.setattr(queue_mod, "Session", lambda engine: _FakeSessionCtx(rows))

    m = QueueManager(max_queue_len=5)
    m._ensure_workers = lambda: None  # type: ignore[assignment]
    m.start()

    assert "align-1" in m._jobs and m._jobs["align-1"].kind == "align"
    assert "rediarize-2" in m._jobs and m._jobs["rediarize-2"].kind == "rediarize"
    assert fake.queued == [], "align/rediarize-Zombies brauchen kein set_queued (kein transcribe)"


def test_enqueue_align_mit_eigenem_key_kein_konflikt(qm_no_worker):
    """Change 155 (Schritt 4): align-Job nutzt String-Key — die Recording
    kann parallel als transcribe-Job (int-Key) in der Queue sein.

    qm_no_worker: ohne Worker bleibt Job 7 queued → position deterministisch.
    """
    qm_no_worker.enqueue(7, None, "ps-pk-onnx")                     # transcribe: key=7
    pos = qm_no_worker.enqueue(7, None, "ps-pk-onnx", kind="align", key="align-7")
    assert pos >= 1
    assert 7 in qm_no_worker._jobs and qm_no_worker._jobs[7].kind == "transcribe"
    assert "align-7" in qm_no_worker._jobs and qm_no_worker._jobs["align-7"].kind == "align"
    # Doppel-Enqueue desselben align-Jobs → QueueError
    try:
        qm_no_worker.enqueue(7, None, "ps-pk-onnx", kind="align", key="align-7")
        assert False, "Doppel-Enqueue desselben Keys muss QueueError werfen"
    except queue_mod.QueueError:
        pass
    qm_no_worker.cancel(7, user_id=None)  # transcribe-Job räumen


def test_worker_dispatch_align_ohne_set_processing(qm, monkeypatch):
    """Change 155 (Schritt 4): align-Jobs laufen über run_align_job —
    set_processing (leert text/segments!) darf NICHT aufgerufen werden."""
    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    started = threading.Event()
    seen = []

    def fake_run_align(rec_id, job=None):
        seen.append(("align", rec_id, job.kind if job else None))
        started.set()

    from app import service as _svc_mod
    monkeypatch.setattr(_svc_mod, "run_align_job", fake_run_align)
    qm.enqueue(9, None, "ps-pk-onnx", kind="align", key="align-9")
    assert started.wait(timeout=5)
    assert seen == [("align", 9, "align")]
    assert fake.processing == [], "align-Job darf set_processing NICHT auslösen"
    qm.stop()


def test_worker_dispatch_peaks_und_vad(qm, monkeypatch):
    """Change 155 (Schritt 6): peaks/vad-Jobs laufen über die Router-
    Dispatch-Ziele — set_processing (leert text/segments!) darf NICHT
    aufgerufen werden."""
    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)

    from app.routers import models as _models_mod
    from app.routers import recordings as _rec_mod

    seen_peaks = threading.Event()
    seen_vad = threading.Event()
    monkeypatch.setattr(_rec_mod, "run_peaks_job", lambda rec_id: seen_peaks.set())
    monkeypatch.setattr(_models_mod, "run_vad_download_job", lambda: seen_vad.set())

    qm.enqueue(11, None, "peaks", kind="peaks", key="peaks-11")
    qm.enqueue(0, None, "ops", kind="vad", key="vad-download")
    assert seen_peaks.wait(timeout=5), "peaks-Job kam nie im Worker an"
    assert seen_vad.wait(timeout=5), "vad-Job kam nie im Worker an"
    assert fake.processing == [], "peaks/vad dürfen set_processing NICHT auslösen"
    qm.stop()


def test_enqueue_persistiert_job_row(qm_no_worker, job_db):
    """Change 155 (Schritt 2): enqueue spiegelt den Job in die DB."""
    from sqlmodel import Session, select

    from app.models import Job

    qm_no_worker.enqueue(7, None, "ps-pk-onnx", kind="transcribe", key=7)
    qm_no_worker.enqueue(9, None, "ps-pk-onnx", kind="align", key="align-9",
                         payload={"separate_backend": "htdemucs"})
    with Session(job_db) as s:
        rows = s.exec(select(Job)).all()
    assert {r.key for r in rows} == {"7", "align-9"}
    by_key = {r.key: r for r in rows}
    assert by_key["7"].kind == "transcribe" and by_key["7"].status == "queued"
    assert by_key["7"].rec_id == 7
    assert by_key["align-9"].kind == "align"
    assert by_key["align-9"].rec_id == 9
    import json as _json

    assert _json.loads(by_key["align-9"].payload) == {"separate_backend": "htdemucs"}


def test_worker_setzt_job_row_done(qm, monkeypatch, job_db):
    """Change 155 (Schritt 2): Worker-Lifecycle schreibt running → done."""
    from sqlmodel import Session, select

    from app.models import Job

    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)

    from app import service as _svc_mod

    done = threading.Event()
    # queue.process_recording ist die beim Import gebundene Referenz —
    # dort mocken, nicht am service-Modul.
    monkeypatch.setattr(queue_mod, "process_recording",
                        lambda rec_id, backend=None, job=None: done.set())

    qm.enqueue(7, None, "ps-pk-onnx", kind="transcribe", key=7)
    assert done.wait(timeout=5), "Worker kam nie durch"
    import time as _t

    row = None
    deadline = _t.time() + 5
    while _t.time() < deadline:
        with Session(job_db) as s:
            row = s.exec(select(Job).where(Job.key == "7")).first()
        if row is not None and row.status == "done":
            break
        _t.sleep(0.05)
    assert row is not None and row.status == "done"
    assert row.started_at is not None and row.finished_at is not None


def test_cancel_setzt_job_row_cancelled(qm_no_worker, job_db):
    """Change 155 (Schritt 2): cancel() markiert die Row als cancelled."""
    from sqlmodel import Session, select

    from app.models import Job

    qm_no_worker.enqueue(7, 1, "ps-pk-onnx", kind="transcribe", key=7)
    assert qm_no_worker.cancel(7, 1) is True
    with Session(job_db) as s:
        row = s.exec(select(Job).where(Job.key == "7")).first()
    assert row is not None and row.status == "cancelled"
    assert row.finished_at is not None
