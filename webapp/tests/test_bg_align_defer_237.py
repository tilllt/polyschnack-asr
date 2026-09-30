"""Change 237 — Hintergrund-Alignment: Folge-Auftrag erst nach dem Abmelden.

Befund (KI-Box, 30.09.2026): ``service.process_recording`` reihte das
Forced-Alignment direkt aus dem laufenden Transkriptions-Job heraus ein. Der
Ein-Job-Wächter (Change 173) sah diesen Job aber noch in ``_jobs`` und lehnte
ab: „recording <id> already has an active job". Folge: seit Wochen entstand
kein automatisches Alignment mehr — Belege: 7× ``bg-align: enqueue
fehlgeschlagen`` in 24 h (rec 336–362), jüngster align-Job der Datenbank vom
19.09.2026, 103 von 116 Aufnahmen ohne align-Job.

Lösung: ``enqueue_after_current`` merkt den Auftrag am Job vor, der Worker
reiht ihn unmittelbar nach ``_jobs.pop(key)`` ein (``_run_deferred``) — dann
ist kein Job der Aufnahme mehr aktiv und der Wächter greift ins Leere.
"""
from __future__ import annotations

import threading

import pytest

from app import queue as queue_mod
from app.queue import QueueError, QueueManager


class _FakeCrud:
    """Stand-in für app.crud im Queue-Modul (DB-frei)."""

    def __init__(self) -> None:
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


def _manager(tmp_path, monkeypatch, *, start: bool = False, max_len: int = 20):
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(
        f"sqlite:///{tmp_path / 'bg_align_defer.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.db.engine", eng)  # queue.py liest db.engine zur Laufzeit

    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(
        queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)

    m = QueueManager(max_queue_len=max_len)
    if start:
        m.start()
    else:
        monkeypatch.setattr(m, "_ensure_workers", lambda: None)
    return m, fake


def test_folgejob_wartet_auf_das_abmelden(tmp_path, monkeypatch):
    """Der Wächter bleibt scharf — der Folge-Auftrag umgeht ihn nur zeitlich."""
    q, _ = _manager(tmp_path, monkeypatch)
    q.enqueue(7, None, "ps-pk-onnx")  # transcribe, Key = 7
    job = q._jobs[7]

    # Solange der Job läuft, ist jeder zweite Job derselben Aufnahme verboten:
    with pytest.raises(QueueError):
        q.enqueue(7, None, "ps-pk-onnx", kind="align", key="align-7")

    # Vorgemerkt geht es — aber er liegt noch NICHT in der Queue.
    assert q.enqueue_after_current(job, 7, "ps-pk-onnx", kind="align", key="align-7") is True
    assert "align-7" not in q._jobs

    # Abmelden wie der Worker (pop → _run_deferred): jetzt ist der Weg frei.
    q._jobs.pop(7)
    q._run_deferred(job)
    assert "align-7" in q._jobs
    assert q._jobs["align-7"].kind == "align"
    assert job.deferred == [], "der Auftrag darf nur einmal eingereiht werden"

    # Zweiter Durchlauf reiht nichts nach.
    q._jobs.pop("align-7")
    q._run_deferred(job)
    assert "align-7" not in q._jobs


def test_folgejob_ohne_laufenden_job_sofort(tmp_path, monkeypatch):
    """Direktaufruf außerhalb der Warteschlange (job=None) reiht sofort ein."""
    q, _ = _manager(tmp_path, monkeypatch)
    assert q.enqueue_after_current(None, 5, "ps-pk-onnx", kind="align", key="align-5") is True
    assert "align-5" in q._jobs


def test_folgejob_meldet_fehler_statt_zu_werfen(tmp_path, monkeypatch):
    """Ist die Aufnahme inzwischen anders belegt, bleibt es bei einer Meldung —
    ein abgeschlossener Job darf daran nicht scheitern."""
    q, _ = _manager(tmp_path, monkeypatch)
    q.enqueue(9, None, "ps-pk-onnx", kind="align", key="align-9")
    assert q.enqueue_after_current(None, 9, "ps-pk-onnx", kind="align", key="align-9") is False
    assert q._jobs["align-9"].status == "queued"


def test_worker_reiht_hintergrund_alignment_nach_abmeldung_ein(tmp_path, monkeypatch):
    """Ende-zu-Ende: Der Worker führt den Transkriptions-Job aus, der das
    Alignment vormerkt — und reiht es danach wirklich ein."""
    q, _ = _manager(tmp_path, monkeypatch, start=True, max_len=5)
    lief = threading.Event()
    gestartet: list = []

    def fake_process(rec_id, backend=None, job=None):
        # Genau das tut service.process_recording:
        q.enqueue_after_current(job, rec_id, backend or "", kind="align",
                                key=f"align-{rec_id}")

    def fake_align(rec_id, job=None):
        gestartet.append((rec_id, job.kind if job else None))
        lief.set()

    monkeypatch.setattr(queue_mod, "process_recording", fake_process)
    from app import service as service_mod

    monkeypatch.setattr(service_mod, "run_align_job", fake_align)

    q.enqueue(11, None, "ps-pk-onnx")
    assert lief.wait(timeout=5), "Hintergrund-Alignment wurde nicht eingereiht"
    assert gestartet == [(11, "align")]
    q.stop()
