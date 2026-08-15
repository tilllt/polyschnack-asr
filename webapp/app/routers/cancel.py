"""Job-Cancel (2026-08-15): laufende Transkriptionen/Alignments abbrechen.

POST /api/recordings/{rid}/cancel
  - queued:   Job aus der Warteschlange entfernen, Status → uploaded
  - processing: cancel_requested setzen → der Worker bricht zwischen den
    Phasen ab (Status → failed mit 'Abgebrochen (User-Cancel)', Datei bleibt)
  - Timeout-Schutz: Ein hängender Job (z.B. Aligner-Call) wird nach
    max_processing_s automatisch abgebrochen — die Queue blockiert nie
    dauerhaft (Lahmlegung-Fix).
"""
from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ..crud import get_recording_by_uid
from ..db import get_session
from ..queue import queue_manager
from .recordings import _current_user, _ensure_audio_present, ensure_access, _key_cap

router = APIRouter(prefix="/api")


@router.post("/recordings/{rid}/cancel")
def cancel_recording(rid: str, request: Request,
                     session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Laufenden oder wartenden Job abbrechen (Transcribe/Re-Transcribe).

    - queued: wird aus der Warteschlange genommen (Status → uploaded)
    - processing: der Worker stoppt nach der aktuellen Phase
      (ASR/Chunk/Diar/Align-Gruppe) und markiert die Aufnahme als failed
      mit 'Abgebrochen (User-Cancel)' — die Datei bleibt erhalten.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))
    _ensure_audio_present(rec)

    from ..identity import current_identity

    ident = current_identity(request, session)
    is_admin = bool(getattr(ident.user, "is_admin", False))

    if rec.id is None:
        raise HTTPException(status_code=409, detail="recording has no id")
    ok = queue_manager.cancel(rec.id, uid, is_admin=is_admin)
    if not ok:
        # Kein aktiver Job (weder queued noch processing) → nichts zu tun.
        # Auch 'done'/'failed' sind idempotent beantwortbar: 200 mit Hinweis.
        return {"cancelled": False, "status": rec.status, "note": "no active job"}
    return {"cancelled": True, "status": "cancelled"}
