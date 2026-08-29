"""Endpoint-bound transcription queue (Task 6, Decisions 3 & 7).

Every job is bound to an endpoint (backend) and occupies one slot of that
endpoint's capacity (``service.concurrency``). The overall concurrency is the
sum of the capacities of the *available* endpoints — there is NO global
concurrency setting (Decision 3).

An endpoint with active jobs cannot be stopped (Decision 7): the admin API
checks ``active_jobs_for(name)`` before allowing a stop.

Job lifecycle: queued -> processing -> (removed on completion). Cancellation
is only possible while queued; a running transcription finishes its endpoint
(the admin stop-guard is the mechanism that protects it).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from . import crud
from .db import engine
from .service import process_recording
from .service_registry import available_services, get_service

log = logging.getLogger(__name__)


class QueueError(RuntimeError):
    """Base queue error."""


class QueueFullError(QueueError):
    """Raised when the queue is at capacity."""


#: Change 155: processing-Recordings mit jüngerem updated_at gelten beim
#: Start als „läuft evtl. noch" (Restart-Race) und werden NICHT wieder
#: aufgenommen — der Stale-Watchdog übernimmt sie später. Ältere gelten
#: als sicher tot (Crash/Deploy) → re-enqueue (Zombie-Fix).
RECOVER_PROCESSING_STALE_S = int(
    os.getenv("POLYSCHNACK_RECOVER_PROCESSING_STALE_S", "120")
)


@dataclass
class Job:
    """Queue-Eintrag für ein Recording.

    ``cancel_requested`` (2026-08-15): Wird vom Cancel-Endpoint gesetzt —
    der Worker prüft das Flag zwischen den Phasen und bricht ab. Damit
    lassen sich auch LAUFENDE Jobs abbrechen, nicht nur queued.
    """
    rec_id: int
    user_id: Optional[int]
    backend: str
    status: str = "queued"  # queued | processing
    seq: int = 0            # FIFO order
    priority: int = 0       # 0 = registriert, 1 = anonym (Task B6)
    cancel_requested: bool = False  # 2026-08-15: Cancel für laufende Jobs
    started_at: Optional[float] = None  # epoch-s, für Job-Timeout

    @property
    def running_s(self) -> float:
        if self.started_at is None:
            return 0.0
        import time
        return time.time() - self.started_at


class QueueManager:
    """FIFO queue with one semaphore per endpoint (Task B6: Prioritäten)."""

    def __init__(self, max_queue_len: int = 20, max_processing_s: int = 3600):
        self._max_queue_len = max_queue_len
        #: Job-Timeout (2026-08-15): Ein hängender Job (z.B. Aligner-Call)
        #: darf die Queue nie dauerhaft blockieren. Läuft ein Job länger,
        #: wird er als failed markiert und das Semaphore freigegeben.
        self._max_processing_s = max_processing_s
        self._lock = threading.Lock()
        self._jobs: Dict[int, Job] = {}
        self._fifo: "queue.PriorityQueue" = queue.PriorityQueue()
        self._semaphores: Dict[str, threading.Semaphore] = {}
        self._threads: List[threading.Thread] = []
        self._stop = threading.Event()
        self._seq = 0
        self._started = False

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        self._ensure_workers()
        self._recover_queued()
        log.info("QueueManager started (%d workers)", len(self._threads))

    def _recover_queued(self) -> None:
        """Change 143: Webapp-Neustart darf queued-Jobs nicht verwaist lassen.

        User-Befund 2026-08-28: „Re-Transcribe wird nur zur Queue
        hinzugefügt und fängt nicht an". Ursache: Der In-Memory-Manager
        kennt nach einem Neustart nur Jobs, die danach enqueued wurden —
        DB-Jobs mit status='queued' (Run angelegt, aber der alte Prozess
        starb vor der Verarbeitung) startet nie ein Worker; die UI zeigt
        dauerhaft „in Warteschlange". Beim Start werden sie wieder in den
        Manager geladen (Priorität 0, FIFO-Hinten). Vorsicht: Läuft ein
        Re-Enqueue gegen einen inzwischen manuell gecancelten Job, bricht
        der Cancel-Guard im Worker das Starten ab (kein Doppelstart).

        Change 155: Auch `processing`-Zombies werden aufgenommen — aber nur,
        wenn der letzte DB-Write sicher alt ist (Prozess tot durch Crash oder
        Deploy). User-Befund 2026-08-29: Ein Deploy/Restart während einer
        laufenden Transkription killte den Job — die Recording klebte ewig auf
        „processing", obwohl kein Worker mehr lief (RAM-Job weg). Frische
        `updated_at`-Werte werden übersprungen (der alte Prozess könnte noch
        schreiben — Restart-Race; der Stale-Watchdog übernimmt später).
        Aufgenommene processing-Jobs werden via set_queued in einen
        konsistenten Zustand gebracht (frischer Heartbeat; Text/Segmente werden
        geleert — sie waren beim Abbruch ohnehin noch nicht geschrieben).
        """
        try:
            from .models import Recording  # lokaler Import (Zyklus-Vermeidung)

            with Session(engine) as session:
                rows = session.query(Recording).filter(
                    Recording.status.in_(["queued", "processing"])
                ).all()
        except Exception:
            log.exception("QueueManager recover failed")
            return
        if not rows:
            return
        now = dt.datetime.now(dt.timezone.utc)
        processing_recovered: List[Any] = []
        with self._lock:
            for rec in rows:
                if rec.id in self._jobs:
                    continue
                if rec.status == "processing":
                    updated = getattr(rec, "updated_at", None)
                    if updated is not None:
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=dt.timezone.utc)
                        if (now - updated).total_seconds() < RECOVER_PROCESSING_STALE_S:
                            # läuft evtl. noch → nicht doppelt starten
                            continue
                    processing_recovered.append(rec)
                self._seq += 1
                self._jobs[rec.id] = Job(
                    rec_id=rec.id, user_id=rec.user_id, backend=rec.backend or "",
                    status="queued", seq=self._seq,
                )
        for rec in processing_recovered:
            # Change 155: processing-Zombie → konsistent queued setzen
            # (gleicher Pfad wie enqueue), damit der Worker ihn normal
            # verarbeitet und der Run-Status zusammenpasst.
            try:
                with Session(engine) as session:
                    crud.set_queued(session, rec.id, rec.backend or "")
            except Exception:
                log.exception("QueueManager recover: set_queued fehlgeschlagen (rec_id=%s)", rec.id)
        for rec in rows:
            if rec.id not in self._jobs:
                continue
            self._fifo.put((0, self._jobs[rec.id].seq, rec.id))
        log.info(
            "QueueManager: %d verwaiste queued/processing-Jobs wieder aufgenommen (%d processing-Zombies)",
            len([r for r in rows if r.id in self._jobs]), len(processing_recovered),
        )

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._started = False

    def _ensure_workers(self) -> None:
        """Workers = sum of capacities of available endpoints (Decision 3)."""
        target = sum(s["concurrency"] for s in available_services())
        with self._lock:
            while len(self._threads) < target:
                t = threading.Thread(target=self._worker_loop, daemon=True)
                t.start()
                self._threads.append(t)

    def _semaphore_for(self, backend: str) -> threading.Semaphore:
        svc = get_service(backend)
        cap = svc["concurrency"] if svc else 1
        with self._lock:
            sem = self._semaphores.get(backend)
            if sem is None:
                sem = threading.Semaphore(cap)
                self._semaphores[backend] = sem
            return sem

    # ---------------------------------------------------------------- api

    def enqueue(self, rec_id: int, user_id: Optional[int], backend: str,
                priority: int = 0) -> int:
        """Queue a job; returns its position on the endpoint. Raises QueueError."""
        with self._lock:
            if rec_id in self._jobs:
                raise QueueError(f"recording {rec_id} is already queued/processing")
            if len(self._jobs) >= self._max_queue_len:
                raise QueueFullError(f"queue full (max {self._max_queue_len} jobs)")
            self._seq += 1
            self._jobs[rec_id] = Job(
                rec_id=rec_id, user_id=user_id, backend=backend,
                status="queued", seq=self._seq, priority=priority,
            )
        with Session(engine) as session:
            crud.set_queued(session, rec_id, backend)
        self._ensure_workers()
        self._fifo.put((priority, self._seq, rec_id))
        return self.position(rec_id)

    def cancel(self, rec_id: int, user_id: Optional[int], is_admin: bool = False) -> bool:
        """Cancel a job — queued ODER processing.

        Queued: aus der Warteschlange entfernen, Status → uploaded.
        Processing (2026-08-15): ``cancel_requested`` setzen — der Worker
        prüft das Flag zwischen den Phasen und bricht ab (Status → failed
        mit klarer Meldung, Datei bleibt).
        Returns False when not cancellable.
        """
        with self._lock:
            job = self._jobs.get(rec_id)
            if job is None:
                return False
            if not is_admin and job.user_id != user_id:
                return False
            if job.status == "queued":
                del self._jobs[rec_id]
                # Reset the DB row so the user can re-transcribe.
                with Session(engine) as session:
                    rec = crud.get_recording(session, rec_id)
                    if rec is not None:
                        rec.status = "uploaded"
                        session.add(rec)
                        session.commit()
                return True
            if job.status == "processing":
                job.cancel_requested = True
                return True
            return False

    def _attach_limits(self, job: Job) -> None:
        """Job-Limits an den Job hängen (Cancel/Timeout-Prüfung in service)."""
        job._max_processing_s = self._max_processing_s  # type: ignore[attr-defined]

    def position(self, rec_id: int) -> int:
        """1-based position among queued jobs on the same endpoint.

        Bearbeitungsreihenfolge (Task B6): Jobs mit niedrigerer Priorität
        kommen immer zuerst (auch wenn sie später enqueued wurden), danach
        FIFO innerhalb derselben Priorität.
        """
        with self._lock:
            mine = self._jobs.get(rec_id)
            if mine is None or mine.status != "queued":
                return 0
            return 1 + sum(
                1 for j in self._jobs.values()
                if j.backend == mine.backend and j.status == "queued"
                and (j.priority < mine.priority
                     or (j.priority == mine.priority and j.seq < mine.seq))
            )

    def active_jobs_for(self, backend: str) -> int:
        """Number of queued+processing jobs on *backend* (admin stop-guard)."""
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if j.backend == backend and j.status in ("queued", "processing")
            )

    def list(self, user_id: Optional[int], is_admin: bool = False) -> List[Dict[str, Any]]:
        """Active jobs for the queue watcher. Foreign jobs are anonymised:
        no filename, no user linkage — only #id, position, status, backend, eta_s."""
        with self._lock:
            jobs = list(self._jobs.values())
        avg_ms = 0.0
        with Session(engine) as session:
            avg_ms = crud.avg_recent_processing_ms(session)
        out: List[Dict[str, Any]] = []
        for j in jobs:
            is_mine = is_admin or j.user_id == user_id
            out.append({
                "job_id": j.rec_id,
                "position": self.position(j.rec_id) if j.status == "queued" else 0,
                "status": j.status,
                "backend": j.backend,
                "eta_s": round(self.position(j.rec_id) * avg_ms / 1000) if avg_ms and j.status == "queued" else None,
                "is_mine": is_mine,
            })
        out.sort(key=lambda d: d["job_id"])
        return out

    def queued_count(self) -> int:
        with self._lock:
            return len(self._jobs)

    # ------------------------------------------------------------ worker

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, rec_id = self._fifo.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._lock:
                job = self._jobs.get(rec_id)
                # Review 2026-08-15 (P1): Cancel-Race — cancel() (queued →
                # aus _jobs entfernt) kann zwischen Dequeue und status=
                # "processing" liegen. Unter dem Lock nachprüfen: Wurde der
                # Job inzwischen gecancelt oder ganz entfernt, NICHT starten
                # (sonst läuft die Transkription trotz Cancel weiter, und
                # ein Re-Enqueue könnte denselben Job doppelt ausführen).
                if job is None or job.cancel_requested or rec_id not in self._jobs:
                    self._fifo.task_done()
                    continue
            sem = self._semaphore_for(job.backend)
            sem.acquire()
            skip = False
            try:
                with self._lock:
                    # Zweiter Recheck nach dem Semaphore-Wait: während der
                    # Worker auf Kapazität wartete, kann der User gecancelt
                    # haben. Dann nicht starten.
                    if job.cancel_requested or rec_id not in self._jobs:
                        skip = True
                    else:
                        job.status = "processing"
                        job.started_at = time.time()
                        self._attach_limits(job)
                if skip:
                    continue
                with Session(engine) as session:
                    crud.set_processing(session, rec_id)
                process_recording(rec_id, backend=job.backend, job=job)
            except Exception:
                log.exception("queue worker failed for rec_id=%s", rec_id)
            finally:
                sem.release()
                with self._lock:
                    self._jobs.pop(rec_id, None)
                self._fifo.task_done()


# Module singleton used by the routers and the lifespan.
queue_manager = QueueManager()
