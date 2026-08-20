"""APIRouter für Annotationen (Change 056 — zeitgebundene Kommentare).

Auth-Konzept (konsistent zu Tags/Segment-Edit):
- Lesen: Zugriff auf die Recording (read reicht)
- Anlegen/Antworten/Bearbeiten/Löschen: write (Owner oder Share)
- Bearbeiten/Löschen: zusätzlich nur Autor oder Admin
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..crud import get_recording_by_uid
from ..db import get_session
from ..models import Annotation, User
from ..permissions import ensure_access

router = APIRouter(prefix="/api")

log = __import__("logging").getLogger(__name__)

_MAX_BODY = 4000


class AnnotationCreate(BaseModel):
    segment_idx: int
    char_start: int = 0
    char_end: int = 0
    body: str


class AnnotationReply(BaseModel):
    body: str


class AnnotationPatch(BaseModel):
    body: str


def _identity(request, session):
    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return identity


def _clean_body(body: str) -> str:
    b = (body or "").strip()
    if not b:
        raise HTTPException(status_code=400, detail="Kommentar darf nicht leer sein")
    if len(b) > _MAX_BODY:
        raise HTTPException(status_code=400, detail=f"Kommentar zu lang (max. {_MAX_BODY} Zeichen)")
    return b


def _time_window(rec, segment_idx: int, char_start: int, char_end: int) -> tuple[float, float]:
    """Zeitfenster der Markierung aus den Wort-Timestamps ableiten.

    Die Zeichen-Positionen zählen wie im Frontend (selectionCharRange):
    Wort-Spans + ein Trenn-Space zwischen Wörtern. Wörter, deren Range die
    Markierung überlappt, liefern start/end; Fallback: Segment-Grenzen.
    """
    segs = rec.segments or []
    if not (0 <= segment_idx < len(segs)):
        raise HTTPException(status_code=400, detail="segment out of range")
    seg = segs[segment_idx]
    words = seg.get("words") or []
    start = char_start
    end = char_end
    if start < 0:
        start = 0
    matched = []
    pos = 0
    for w in words:
        wlen = len(str(w.get("word") or ""))
        if pos + wlen > start and pos < end:
            matched.append(w)
        pos += wlen + 1  # +1 = Trenn-Space
    if matched:
        try:
            s = min(float(w.get("start") or 0.0) for w in matched)
            e = max(float(w.get("end") or (w.get("start") or 0.0) + 1.0) for w in matched)
            return max(0.0, s), max(s, e)
        except (TypeError, ValueError):
            pass
    seg_start = float(seg.get("start") or 0.0)
    seg_end = float(seg.get("end") or seg_start + 1.0)
    return max(0.0, seg_start), max(seg_start, seg_end)


def _serialize(session: Session, ann: Annotation) -> Dict[str, Any]:
    uname: Optional[str] = None
    usub: Optional[str] = None
    if ann.user_id is not None:
        user = session.get(User, ann.user_id)
        if user is not None:
            uname = getattr(user, "name", None) or getattr(user, "username", None) or user.sub
            usub = user.sub
    return {
        "id": ann.id,
        "uid": ann.uid,
        "rec_id": ann.rec_id,
        "user_id": ann.user_id,
        "user_name": uname,
        "user_sub": usub,
        "segment_idx": ann.segment_idx,
        "char_start": ann.char_start,
        "char_end": ann.char_end,
        "start_s": ann.start_s,
        "end_s": ann.end_s,
        "body": ann.body,
        "parent_id": ann.parent_id,
        "created_at": ann.created_at.isoformat() if ann.created_at else None,
        "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Liste + Anlegen (an der Recording)
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/annotations")
def list_annotations(
    rid: str,
    request: Request = None,
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Alle Annotationen einer Aufnahme (flach; Frontend baut Threads)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    identity = _identity(request, session)
    ensure_access(session, rec, identity.user.id, "read", cap=identity.key_level)

    rows = session.exec(
        select(Annotation).where(Annotation.rec_id == rec.id).order_by(Annotation.start_s)
    ).all()
    return [_serialize(session, a) for a in rows]


@router.post("/recordings/{rid}/annotations")
def create_annotation(
    rid: str,
    body: AnnotationCreate,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Neue Top-Level-Annotation (write). Zeitfenster wird aus den
    Wort-Timestamps der Markierung abgeleitet."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    identity = _identity(request, session)
    ensure_access(session, rec, identity.user.id, "write", cap=identity.key_level)

    text = _clean_body(body.body)
    start_s, end_s = _time_window(rec, body.segment_idx, body.char_start, body.char_end)
    ann = Annotation(
        rec_id=rec.id,
        user_id=identity.user.id,
        segment_idx=body.segment_idx,
        char_start=max(0, body.char_start),
        char_end=max(0, body.char_end),
        start_s=start_s,
        end_s=end_s,
        body=text,
    )
    session.add(ann)
    session.commit()
    session.refresh(ann)
    return _serialize(session, ann)


# ---------------------------------------------------------------------------
# Antworten / Bearbeiten / Löschen (an der Annotation)
# ---------------------------------------------------------------------------


def _get_annotation(session: Session, aid: int) -> Annotation:
    ann = session.get(Annotation, aid)
    if ann is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return ann


def _rec_for_annotation(session: Session, ann: Annotation):
    """Recording zu einer Annotation (für Zugriffsprüfung)."""
    from ..models import Recording

    rec = session.get(Recording, ann.rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    return rec


def _ensure_annot_write(session: Session, request: Request, ann: Annotation):
    """write-Zugriff auf die Recording der Annotation."""
    rec = _rec_for_annotation(session, ann)
    identity = _identity(request, session)
    ensure_access(session, rec, identity.user.id, "write", cap=identity.key_level)
    return identity, rec


def _author_or_admin(request: Request, identity, ann: Annotation) -> None:
    """Nur Autor oder Admin darf bearbeiten/löschen."""
    from ..config import settings

    is_admin = settings.OIDC_ENABLED and bool(request.session.get("is_admin"))
    if identity.user.id != ann.user_id and not is_admin:
        raise HTTPException(status_code=403, detail="nur Autor oder Admin")


@router.post("/annotations/{aid}/replies")
def reply_to_annotation(
    aid: int,
    body: AnnotationReply,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Antwort auf eine Top-Level-Annotation (write auf die Recording).

    Die Antwort erbt das Zeitfenster der Top-Level-Annotation.
    """
    parent = _get_annotation(session, aid)
    if parent.parent_id is not None:
        raise HTTPException(status_code=400, detail="Antworten nur auf Top-Level-Annotationen")
    identity, _rec = _ensure_annot_write(session, request, parent)
    text = _clean_body(body.body)
    ann = Annotation(
        rec_id=parent.rec_id,
        user_id=identity.user.id,
        segment_idx=parent.segment_idx,
        char_start=parent.char_start,
        char_end=parent.char_end,
        start_s=parent.start_s,
        end_s=parent.end_s,
        body=text,
        parent_id=parent.id,
    )
    session.add(ann)
    session.commit()
    session.refresh(ann)
    return _serialize(session, ann)


@router.patch("/annotations/{aid}")
def update_annotation(
    aid: int,
    body: AnnotationPatch,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Body editieren — nur Autor oder Admin."""
    ann = _get_annotation(session, aid)
    identity, _rec = _ensure_annot_write(session, request, ann)
    _author_or_admin(request, identity, ann)
    ann.body = _clean_body(body.body)
    ann.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(ann)
    session.commit()
    session.refresh(ann)
    return _serialize(session, ann)


@router.delete("/annotations/{aid}")
def delete_annotation(
    aid: int,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Löschen (Autor oder Admin) inkl. Antworten (Thread-Kaskade)."""
    ann = _get_annotation(session, aid)
    identity, _rec = _ensure_annot_write(session, request, ann)
    _author_or_admin(request, identity, ann)
    replies = session.exec(
        select(Annotation).where(Annotation.parent_id == ann.id)
    ).all()
    for r in replies:
        session.delete(r)
    session.delete(ann)
    session.commit()
    return {"deleted": aid, "replies_deleted": len(replies)}
