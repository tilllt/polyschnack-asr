"""learner_store.py — DB-Schicht für den ETA-Learner (Change 085, Phase 0).

Bildet aus Job-Stichproben (``phase_times_ms`` + Audio-Dauer) die
Faktor-Werte, füttert den puren :class:`RtfLearner` und persistiert dessen
Historie in der ``rtf_estimates``-Tabelle. Align läuft post-done im
Hintergrund-Worker und bekommt einen eigenen Ingest (Bezugsgröße =
Anzahl Align-Gruppen, Einheit ms/Gruppe statt ms/s Audio).
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

from sqlmodel import Session, select

from .db import engine
from .models import RtfEstimate
from .rtf_learner import RtfLearner

log = logging.getLogger(__name__)

#: Minimale Messdauer einer Phase, damit sie als Stichprobe zählt (Rausch-Schutz).
MIN_PHASE_MS = 1.0
#: Minimale Audio-Dauer (s) für eine Faktor-Stichprobe (Division durch 0 vermeiden).
MIN_DURATION_S = 0.5


# ---------------------------------------------------------------------------
# Pure Faktor-Bildung (testbar ohne DB)
# ---------------------------------------------------------------------------

def factor_from_phase(phase_ms: float, duration_s: Optional[float]) -> Optional[float]:
    """Faktor = (phase_ms/1000) / duration_s — None bei ungültiger Basis (Anti-Fake)."""
    if phase_ms is None or phase_ms < MIN_PHASE_MS:
        return None
    if not duration_s or duration_s < MIN_DURATION_S:
        return None
    return (float(phase_ms) / 1000.0) / float(duration_s)


def job_factors(
    phase_times_ms: Dict[str, float],
    duration_s: Optional[float],
) -> Dict[str, float]:
    """Faktor je gemessener Phase; ungültige Stichproben entfallen still."""
    out: Dict[str, float] = {}
    for key, ms in (phase_times_ms or {}).items():
        f = factor_from_phase(ms, duration_s)
        if f is not None:
            out[key] = f
    return out


def align_factor(align_ms: float, n_groups: int) -> Optional[float]:
    """ms pro Align-Gruppe — None bei ungültiger Basis."""
    if align_ms is None or align_ms < MIN_PHASE_MS:
        return None
    if not n_groups or n_groups < 1:
        return None
    return float(align_ms) / float(n_groups)


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------

def load_learner(session: Optional[Session] = None) -> RtfLearner:
    """Learner-Zustand aus der Tabelle laden (leer, wenn nichts gelernt)."""
    learner = RtfLearner()
    own = session is None
    session = session or Session(engine)
    try:
        rows = session.exec(select(RtfEstimate)).all()
        state = {
            "history": {},
            "digest": {},
        }
        for row in rows:
            try:
                state["history"][row.phase_key] = json.loads(row.history_json or "[]")
            except (TypeError, ValueError):
                state["history"][row.phase_key] = []
            if row.digest:
                state["digest"][row.phase_key] = row.digest
        learner.from_state(state)
    finally:
        if own:
            session.close()
    return learner


def save_learner(session: Optional[Session], learner: RtfLearner) -> None:
    """Historie + Digest je Key in die Tabelle schreiben (upsert)."""
    own = session is None
    session = session or Session(engine)
    try:
        state = learner.to_state()
        history = state.get("history") or {}
        digest = state.get("digest") or {}
        for key in sorted(set(history) | set(digest)):
            row = session.get(RtfEstimate, key)
            if row is None:
                row = RtfEstimate(phase_key=key)
            row.history_json = json.dumps(history.get(key, []))
            row.digest = digest.get(key)
            from datetime import datetime, timezone
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
        # Keys, die komplett geleert wurden (reset einzelner Key): löschen
        known = set(history) | set(digest)
        for row in session.exec(select(RtfEstimate)).all():
            if row.phase_key not in known and not history.get(row.phase_key):
                session.delete(row)
        session.commit()
    finally:
        if own:
            session.close()


def reset_estimates(phase_key: Optional[str] = None) -> int:
    """Historie zurücksetzen (ein Key oder alle). Returns: gelöschte Zeilen."""
    with Session(engine) as session:
        if phase_key:
            rows = session.exec(
                select(RtfEstimate).where(RtfEstimate.phase_key == phase_key)
            ).all()
        else:
            rows = session.exec(select(RtfEstimate)).all()
        n = len(rows)
        for row in rows:
            session.delete(row)
        session.commit()
        return n


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_job_sample(
    rec_id: int,
    phase_times_ms: Dict[str, float],
    duration_s: Optional[float],
    *,
    digest: Optional[str] = None,
    session: Optional[Session] = None,
) -> int:
    """Job-Abschluss-Stichprobe: alle gemessenen Phasen → Learner → DB.

    Returns: Anzahl aufgenommener Stichproben. Ungültige Stichproben
    (keine Dauer, Phase < 1 ms) werden verworfen — nie raten.
    """
    factors = job_factors(phase_times_ms, duration_s)
    if not factors:
        return 0
    own = session is None
    session = session or Session(engine)
    try:
        learner = load_learner(session)
        for key, f in factors.items():
            # asr:<backend> wird bei Image-Wechsel invalidiert; andere
            # Phasen-Keys haben keinen Digest (vom Backend unabhängig).
            learner.ingest(key, f, digest=digest if key.startswith("asr:") else None)
        save_learner(session, learner)
        log.info(
            "rtf_learner: rec_id=%s ingest %d sample(s) (duration=%.1fs)",
            rec_id, len(factors), duration_s or 0.0,
        )
        return len(factors)
    finally:
        if own:
            session.close()


def ingest_align_sample(
    rec_id: int,
    n_groups: int,
    align_ms: float,
    *,
    session: Optional[Session] = None,
) -> bool:
    """Align-Stichprobe (ms/Gruppe) aus dem Hintergrund-Worker."""
    f = align_factor(align_ms, n_groups)
    if f is None:
        return False
    own = session is None
    session = session or Session(engine)
    try:
        learner = load_learner(session)
        learner.ingest("align", f)
        save_learner(session, learner)
        log.info("rtf_learner: rec_id=%s align sample: %.1f ms/group (n=%d)",
                 rec_id, f, n_groups)
        return True
    finally:
        if own:
            session.close()
