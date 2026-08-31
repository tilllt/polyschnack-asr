"""Change 183 — Job-Zustandsmaschine (eine Quelle der Wahrheit).

Der persistente Job-Row (models.Job) trägt den Lebenszyklus:
queued → running → done|failed|cancelled + phase + pct + Zeiten.
``job_transition()`` ist der einzige Schreibweg — atomar in der DB.
Die Recording-Ableitungsfelder (status/alignment/diar_status/
progress_*) bleiben bis Phase 3 parallel geschrieben und werden dann
entfernt; die UI liest ab Phase 2 den Job.

Gegenüber den alten Einzel-Feldern:
- phase/pct/Zeiten am Job → kein Restzustand nach skipped/failed
  (Rec-Felder wurden an mehreren Stellen geschrieben/nie geräumt)
- cancel_requested persistiert in der DB → überlebt Restarts
- heartbeat_at am Job → Aktivitäts-Nachweis ohne Rec-Feld-Mix
"""

import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

PHASES = (
    "preparing", "separate", "asr", "diarization",
    "alignment", "finalizing", "postprocessing",
)

#: Endzustände — danach keine phase/pct-Updates mehr sinnvoll.
TERMINAL = ("done", "failed", "cancelled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_transition(
    session,
    row_id: Optional[int],
    *,
    status: Optional[str] = None,
    phase: Optional[str] = None,
    pct: Optional[float] = None,
    error: Optional[str] = None,
    heartbeat: bool = True,
) -> None:
    """Atomarer Zustands-/Fortschritts-Übergang des Job-Rows.

    - erster ``running``-Übergang: started_at setzen
    - Phasen-Wechsel: phase_started_at setzen (Basis für „läuft seit")
    - jeder Aufruf: heartbeat_at aktualisieren (Aktivitäts-Nachweis)
    Fehlende Row (row_id None / nicht gefunden): defensiv nur loggen.
    """
    if row_id is None:
        return
    from .models import Job

    row = session.get(Job, row_id)
    if row is None:
        return
    now = _now()
    if status is not None:
        if status == "running" and row.status != "running":
            row.started_at = now
        row.status = status
        if status in TERMINAL:
            row.heartbeat_at = None  # kein Heartbeat mehr nach dem Ende
            row.finished_at = now  # Change 183: Endzeit wie bisher (queue)
    if phase is not None:
        if phase != row.phase:
            row.phase_started_at = now
        row.phase = phase
    if pct is not None:
        row.pct = pct
    if error is not None:
        row.error = error
    if heartbeat and row.status not in TERMINAL:
        row.heartbeat_at = now
    session.add(row)
    session.commit()


def job_cancelled(session, row_id: Optional[int]) -> bool:
    """Persistenter Cancel-Check — überlebt Restarts (im Gegensatz zum
    In-Memory-Flag der Queue)."""
    if row_id is None:
        return False
    from .models import Job

    row = session.get(Job, row_id)
    return bool(row and row.cancel_requested)


def job_request_cancel(session, row_id: Optional[int]) -> bool:
    """Cancel persistent setzen. Returns False wenn keine Row."""
    if row_id is None:
        return False
    from .models import Job

    row = session.get(Job, row_id)
    if row is None:
        return False
    row.cancel_requested = 1
    session.add(row)
    session.commit()
    return True
