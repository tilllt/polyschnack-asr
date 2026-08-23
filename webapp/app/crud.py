"""CRUD helpers — all database operations as pure functions.

Every function receives an open ``Session`` and operates within it.
No HTTP calls, no business logic, no side effects beyond the DB.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from .models import Recording, RecordingShare, User

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_recording(
    session: Session,
    *,
    original_name: str,
    stored_path: str,
    mime: str,
    size_bytes: int,
    batch_id: Optional[str] = None,
    recorded_at: Optional[dt.datetime] = None,
    source: Optional[str] = None,
    content_hash: Optional[str] = None,
    duration_s: Optional[float] = None,
    user_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
) -> Recording:
    """Insert a new Recording row with status='processing' and return it."""
    rec = Recording(
        original_name=original_name,
        stored_path=stored_path,
        mime=mime,
        size_bytes=size_bytes,
        duration_s=duration_s,
        status="uploaded",
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        content_hash=content_hash,
        user_id=user_id,
        owner_user_id=owner_user_id,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def create_queued_run(
    session: Session,
    rec_id: int,
    *,
    backend: str = "ps-pk-onnx",
    language: Optional[str] = None,
    enable_vad: bool = False,
    enable_diarize: bool = False,
    diarize_num_speakers: Optional[int] = None,
    diarize_min_duration_off: Optional[float] = None,
    diarize_method: Optional[str] = None,
    enable_streaming: bool = False,
    enable_noise_reduce: bool = True,
    enable_enhance: str = "off",
    separate_backend: str = "none",
    enable_punctuation: bool = False,
    enable_llm_enhance: bool = False,
    prompt_template_id: Optional[int] = None,
    delivery_target_id: Optional[int] = None,
    llm_endpoint_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> "TranscriptionRun":
    """Change 099: queued-Run mit den Settings eines Uploads/Imports.

    Das Recording trägt keine Settings-Spalten mehr — die versionierte
    Wahrheit lebt im Run. process_recording übernimmt den ältesten
    queued-Run und stellt ihn auf processing.
    """
    from .models import TranscriptionRun

    run = TranscriptionRun(
        rec_id=rec_id,
        backend=backend,
        language=language,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        diarize_num_speakers=diarize_num_speakers,
        diarize_min_duration_off=diarize_min_duration_off,
        diarize_method=diarize_method,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        separate_backend=separate_backend,
        enable_punctuation=enable_punctuation,
        enable_llm_enhance=enable_llm_enhance,
        prompt_template_id=prompt_template_id,
        delivery_target_id=delivery_target_id,
        llm_endpoint_id=llm_endpoint_id,
        status="queued",
        created_by_user_id=user_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_recording(session: Session, rec_id: int) -> Optional[Recording]:
    """Return the Recording with *rec_id*, or ``None`` if not found."""
    return session.get(Recording, rec_id)


def get_recording_by_uid(session: Session, uid: str) -> Optional[Recording]:
    """Return the Recording with *uid*, or ``None`` if not found."""
    return session.exec(select(Recording).where(Recording.uid == uid)).first()


def list_recordings(
    session: Session, q: Optional[str] = None, user_id: Optional[int] = None,
    include_shares: bool = True,
    sort: str = "date", dir: str = "desc",
    tags: Optional[List[str]] = None,
) -> List[Recording]:
    """Return recordings (Change 054: sortierbar + tag-filtrierbar).

    - *user_id* = ``None`` → only recordings with no owner (public/shared space)
    - *user_id* = ``int`` → recordings belonging to that user **plus** recordings
      shared with them (when *include_shares*).
    - *sort*: ``date`` (created_at, Default) | ``edited`` (updated_at) |
      ``name`` (Titel, Fallback Originalname) | ``filename`` (original_name) |
      ``length`` (duration_s, NULLs ans Ende).
    - *dir*: ``desc`` (Default) | ``asc``.
    - *tags*: ODER-Filter — eine Aufnahme gehört zum Ergebnis, wenn
      mindestens eines der Tags gesetzt ist (case-insensitive).

    Sortierung passiert nach dem Laden in Python (stabil, einheitlich —
    bei der Listen-Größe der Webapp irrelevant für die Performance).
    """
    stmt = select(Recording)
    if user_id is not None:
        owned = Recording.user_id == user_id
        if include_shares:
            shared = Recording.id.in_(
                select(RecordingShare.rec_id).where(RecordingShare.user_id == user_id)
            )
            stmt = stmt.where(owned | shared)
        else:
            stmt = stmt.where(owned)
    else:
        stmt = stmt.where(Recording.user_id.is_(None))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            Recording.original_name.ilike(term) | Recording.text.ilike(term)  # type: ignore[union-attr]
        )
    rows = list(session.exec(stmt).all())

    if tags:
        wanted = {t.lower() for t in tags if t}
        if wanted:
            rows = [
                r for r in rows
                if wanted & {t.lower() for t in (r.tags or [])}
            ]

    _EPOCH = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    keys = {
        "date": lambda r: r.created_at or _EPOCH,
        "edited": lambda r: r.updated_at or _EPOCH,
        # Titel alphabetisch (Fallback Originalname), case-insensitive.
        "name": lambda r: (r.title or r.original_name or "").lower(),
        "filename": lambda r: (r.original_name or "").lower(),
    }
    if sort == "length":
        # Dauer: noch nicht gemessene (None) IMMER ans Ende — unabhängig
        # von der Richtung (bei desc wären sie sonst vorn, weil None < Zahl).
        with_val = [r for r in rows if r.duration_s is not None]
        without_val = [r for r in rows if r.duration_s is None]
        with_val.sort(key=lambda r: r.duration_s, reverse=(dir == "desc"))
        rows = with_val + without_val
    else:
        key = keys.get(sort, keys["date"])
        rows.sort(key=key, reverse=(dir == "desc"))
    return rows


def list_recordings_missing_peaks(session: Session, limit: int = 3) -> list[Recording]:
    """Älteste Recordings OHNE Waveform-Peaks ODER OHNE Playback-Preview —
    über ALLE User (auch anon).

    Für den periodischen Peaks-/Preview-Backfill (2026-08-15): der frühere
    Nachzug bei GET /recordings startete für jede peaks-lose Aufnahme einen
    eigenen ffmpeg-Thread → bei vielen alten Dateien feuerten Dutzende
    Voll-Decodes gleichzeitig (CPU/RAM-Kollaps, Seite ewig langsam). Der
    Backfill-Loop arbeitet seriell mit kleinem Limit pro Durchlauf.

    SQLite speichert die JSON-Spalte als Text `'null'` (nicht SQL-NULL) —
    deshalb cast-Vergleich statt ``.is_(None)``. Leere Listen (`[]`) sind
    der „versucht, keine Peaks möglich"-Marker und werden NICHT erneut
    gefunden (kein Endlos-Retry bei kaputten Dateien).
    """
    from sqlalchemy import cast, or_, String

    stmt = (
        select(Recording)
        .where(or_(
            cast(Recording.waveform_peaks, String) == "null",
            Recording.waveform_peaks.is_(None),  # type: ignore[union-attr]
            Recording.preview_path.is_(None),  # type: ignore[union-attr]
        ))
        .order_by(Recording.id.asc())  # type: ignore[arg-type]
        .limit(limit)
    )
    return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def current_run_for(session: Session, rec) -> Optional["TranscriptionRun"]:
    """Change 099: aktueller Run eines Recordings (current_run_id; Fallback
    jüngster Run). None wenn keiner existiert — Aufrufer nutzen Defaults."""
    from .models import TranscriptionRun as _Run

    if rec.current_run_id:
        run = session.get(_Run, rec.current_run_id)
        if run is not None:
            return run
    return session.exec(select(_Run).where(
        _Run.rec_id == rec.id).order_by(_Run.id.desc())).first()


def set_processing(session: Session, rec_id: int) -> Optional[Recording]:
    """Reset a recording to processing state, clearing previous results.

    ``duration_s`` is NOT cleared here so the frontend can show a meaningful
    ETA from the upload-time estimate while the ASR worker is still starting up.
    The worker will overwrite it with the decoded duration when it finishes.
    ``progress_pct`` starts at 1 (not 0) so the frontend does not hide the ETA.
    """
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = "processing"
    rec.text = None
    rec.segments = None
    rec.language = None
    rec.error = None
    # keep duration_s — the upload already gave us a rough estimate for ETA
    rec.processing_ms = None
    rec.progress_pct = 1  # 1 instead of 0 so fmtETA can compute
    # Change 035: Heartbeat-Zeitstempel frisch starten — sonst zeigt die UI
    # nach Re-Transcribe sofort einen uralten „seit Xs"-Wert vom letzten Lauf.
    rec.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
    rec.phase_started_at = rec.last_heartbeat_at
    # Change 082: Job-Beginn — Basis für ETA-Rest und „verarbeitet seit Xs".
    rec.processing_started_at = rec.last_heartbeat_at
    # Change 086: Reserve (konservative Obergrenze) für die virtuelle
    # Credit-Abrechnung — nie blockierend, Fehler → keine Reserve.
    try:
        from .eta import _estimate_eta_s
        from .learner_store import load_learner
        from .pricing import backend_cost_per_minute, reserve_cents

        learner = load_learner()
        run = current_run_for(session, rec)  # Change 099: Settings aus dem Run
        core = _estimate_eta_s(
            rec.duration_s, rec.backend,
            enable_vad=bool(run and run.enable_vad),
            enable_diarize=bool(run and run.enable_diarize),
            diarize_method=run.diarize_method if run else None,
            enable_noise_reduce=True if run is None else bool(run.enable_noise_reduce),
            enable_enhance="off" if run is None else (run.enable_enhance or "off"),
            separate_backend="none" if run is None else (run.separate_backend or "none"),
            learner=learner,
        )
        factor_high = core[2] if core else None
        rec.reserved_cents = reserve_cents(
            rec.duration_s, factor_high,
            backend_cost_per_minute(rec.backend),
        )
    except Exception:
        rec.reserved_cents = None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def set_queued(session: Session, rec_id: int, backend: str) -> Optional[Recording]:
    """Mark a recording as queued for transcription on *backend* (Task 6)."""
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = "queued"
    rec.backend = backend
    rec.text = None
    rec.segments = None
    rec.error = None
    rec.progress_pct = 1  # keep the frontend ETA visible
    # Change 035: Heartbeat-Zeitstempel frisch starten (wie set_processing) —
    # die Wartezeit beginnt erst mit dem Enqueue, nicht mit dem letzten Lauf.
    rec.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
    rec.phase_started_at = rec.last_heartbeat_at
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def list_queued(session: Session) -> List[tuple]:
    """(rec_id, backend, user_id) for all queued recordings (re-enqueue on boot)."""
    stmt = select(Recording).where(Recording.status == "queued")
    return [(r.id, r.backend, r.user_id) for r in session.exec(stmt)]


def avg_recent_processing_ms(session: Session, limit: int = 20) -> float:
    """Mean processing_ms of the last *limit* completed recordings (ETA estimate)."""
    stmt = (
        select(Recording.processing_ms)
        .where(Recording.status == "done", Recording.processing_ms.is_not(None))
        .order_by(Recording.id.desc())
        .limit(limit)
    )
    vals = [r for r in session.exec(stmt) if r]
    return (sum(vals) / len(vals)) if vals else 0.0


def update_result(
    session: Session,
    rec_id: int,
    *,
    status: str,
    text: str,
    duration_s: Optional[float],
    language: Optional[str],
    segments: Optional[List[Dict[str, Any]]],
    processing_ms: float,
    error: Optional[str],
    progress_pct: int = 100,
    waveform_peaks: Optional[List[float]] = None,
    phase_times_ms: Optional[Dict[str, float]] = None,
) -> Optional[Recording]:
    """Persist the transcription result (success or failure) for *rec_id*."""
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = status
    rec.text = text
    if duration_s is not None:
        rec.duration_s = duration_s
    rec.language = language
    rec.segments = segments
    # Change 009: neue ASR-Segmente (Transcribe/Retranscribe) heben die
    # manuelle Aufteilung auf — Auto-Aufteilung gilt wieder.
    if segments is not None:
        rec.segments_manual = False
    rec.processing_ms = processing_ms
    # Change 085: Phasen-Zeiten persistieren (Stichproben für rtf_learner).
    if phase_times_ms is not None:
        rec.phase_times_ms = phase_times_ms
    # Change 086: Ist-Kosten berechnen + buchen (nie den Abschluss brechen).
    if status == "done":
        try:
            from .ledger import book_job_cost
            from .pricing import backend_cost_per_minute, calculate_job_cost

            rate = backend_cost_per_minute(rec.backend)
            cost = calculate_job_cost(
                rec.phase_times_ms, rec.duration_s, rec.backend,
                backend_cost_per_minute_eur=rate,
                llm_seconds=(rec.phase_times_ms or {})
                .get("punc_truecase", 0.0) / 1000.0,
            )
            rec.cost_cents = cost
            if cost > 0 and rec.user_id is not None:
                book_job_cost(session, rec.user_id, rec_id, cost)
        except Exception:
            log.exception("credits: cost booking failed for rec_id=%d", rec_id)
    rec.error = error
    rec.progress_pct = progress_pct
    rec.updated_at = dt.datetime.now(dt.timezone.utc)
    if waveform_peaks is not None:
        rec.waveform_peaks = waveform_peaks
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def _delete_recording_children(session: Session, rec: Recording) -> None:
    """Abhängige Zeilen einer Aufnahme löschen (Datenschutz: „mit allen Daten").

    TranscriptVersion (komplette Transkript-Texte + Segmente) und
    RecordingShare (Zugriffs-Zuordnungen) hängen ohne CASCADE an der
    Recording — ohne diesen Aufruf blieben die Inhalte nach dem Löschen
    in der DB zurück.
    """
    from .models import RecordingShare, TranscriptVersion

    for v in session.exec(
        select(TranscriptVersion).where(TranscriptVersion.rec_id == rec.id)
    ).all():
        session.delete(v)
    for sh in session.exec(
        select(RecordingShare).where(RecordingShare.rec_id == rec.id)
    ).all():
        session.delete(sh)


def delete_recording(session: Session, rec_id: int) -> Optional[Recording]:
    """Delete the row for *rec_id* and return it (for file cleanup).

    Löscht auch alle abhängigen Zeilen (Transkript-Versionen, Shares) —
    Datenschutz: Löschen entfernt die Daten vollständig aus der DB, nicht
    nur die Aufnahme selbst.

    Returns ``None`` if the row does not exist.
    """
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    _delete_recording_children(session, rec)
    session.delete(rec)
    session.commit()
    return rec


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def get_stats(session: Session, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Return aggregate counts and totals across all recordings (or per user)."""
    stmt = select(Recording)
    if user_id is not None:
        stmt = stmt.where(Recording.user_id == user_id)
    else:
        stmt = stmt.where(Recording.user_id.is_(None))
    rows = list(session.exec(stmt).all())
    total = len(rows)
    done = sum(1 for r in rows if r.status == "done")
    processing = sum(1 for r in rows if r.status == "processing")
    uploaded = sum(1 for r in rows if r.status == "uploaded")
    failed = sum(1 for r in rows if r.status == "failed")
    total_audio_s = sum(r.duration_s or 0.0 for r in rows)
    total_processing_ms = sum(r.processing_ms or 0.0 for r in rows)
    total_size_bytes = sum(r.size_bytes or 0 for r in rows)
    return {
        "total": total,
        "done": done,
        "processing": processing,
        "uploaded": uploaded,
        "failed": failed,
        "total_audio_s": total_audio_s,
        "total_processing_ms": total_processing_ms,
        "total_size_bytes": total_size_bytes,
    }


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def get_or_create_user(
    session: Session,
    *,
    sub: str,
    preferred_username: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> User:
    user = session.exec(select(User).where(User.sub == sub)).first()
    if user:
        if preferred_username:
            user.preferred_username = preferred_username
        if email:
            user.email = email
        if name:
            user.name = name
        session.add(user)
        return user
    user = User(
        sub=sub,
        preferred_username=preferred_username,
        email=email,
        name=name,
    )
    session.add(user)
    session.flush()
    # Change 086: Startguthaben (virtuell) — einmalig beim ersten Anlegen.
    try:
        from .ledger import SIGNUP_BONUS_CENTS
        from .models import CreditLedger

        user.credits_cents = SIGNUP_BONUS_CENTS
        session.add(CreditLedger(
            user_id=user.id, delta_cents=SIGNUP_BONUS_CENTS,
            reason="signup_bonus",
        ))
    except Exception:
        pass  # Bonus optional — nie den User-Fluss brechen
    return user


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def set_progress(session: Session, rec_id: int, pct: int, note: Optional[str] = None) -> None:
    """Update progress_pct (+ optional Phasen-Hinweis) for a recording.

    Change 011 (2026-08-17): Jeder Aufruf aktualisiert zusätzlich
    ``last_heartbeat_at`` (Aktivitäts-Nachweis — die UI unterscheidet damit
    „läuft, kein messbarer Fortschritt" von „eingefroren"). Ändert sich die
    Phasen-Note, wird ``phase_started_at`` gesetzt (Beginn der neuen Phase —
    Basis für „Phase läuft seit Xs" im Frontend).
    """
    rec = session.get(Recording, rec_id)
    if rec:
        now = dt.datetime.now(dt.timezone.utc)
        rec.progress_pct = pct
        rec.updated_at = now
        rec.last_heartbeat_at = now
        if note is not None:
            if note != rec.progress_note:
                rec.phase_started_at = now
            rec.progress_note = note
        session.add(rec)
        session.commit()
