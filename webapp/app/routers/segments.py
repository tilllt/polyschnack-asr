"""PATCH endpoint for inline segment text editing."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session
from ..permissions import ensure_access

router = APIRouter(prefix="/api")


class SegmentUpdate(BaseModel):
    text: str


class SpeakerRename(BaseModel):
    from_speaker: str
    to_speaker: str


@router.post("/recordings/{rid}/speaker-rename")
def rename_speaker(
    rid: str,
    body: SpeakerRename,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Ersetzt ``speaker`` in ALLEN Segmenten einer Aufnahme (global).

    User-Anforderung: Doppelklick auf einen Speaker-Namen in der GUI →
    umbenennen → der neue Name gilt an allen Vorkommen (Segmente, SRT/VTT,
    Versionen ab jetzt). Auth + Zugriff wie beim Segment-Edit (write).
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    from_speaker = body.from_speaker.strip()
    to_speaker = body.to_speaker.strip()
    if not from_speaker or not to_speaker:
        raise HTTPException(
            status_code=400, detail="from_speaker and to_speaker must not be empty"
        )

    # Tiefe Kopie (In-Place-Mutation würde SQLAlchemy-Change-Erkennung umgehen)
    import json as _json

    segments = _json.loads(_json.dumps(rec.segments or []))
    renamed = 0
    for s in segments:
        if s.get("speaker") == from_speaker:
            s["speaker"] = to_speaker
            renamed += 1
    if renamed == 0:
        raise HTTPException(
            status_code=400, detail=f"speaker '{from_speaker}' not found in segments"
        )

    rec.segments = list(segments)  # neue Referenz → SQLAlchemy erkennt die Änderung
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text, "renamed": renamed}


@router.patch("/recordings/{rid}/segments/{idx}")
def update_segment(
    rid: str,
    idx: int,
    body: SegmentUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Update the text of a single segment in-place."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    # Tiefe Kopie: neue dicts → SQLAlchemy erkennt die Zuweisung als Änderung
    # (In-Place-Mutation der JSON-Liste würde auch die "alte" Liste verändern,
    # sodass alte == neue und der Commit stillschweigend übersprungen wird).
    import json as _json

    segments = _json.loads(_json.dumps(rec.segments or []))
    if idx < 0 or idx >= len(segments):
        raise HTTPException(status_code=404, detail="segment not found")

    new_text = body.text.strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    segments[idx]["text"] = new_text
    # Rebuild words from edited text so karaoke still works
    text_words = new_text.split()
    seg_start = segments[idx].get("start", 0)
    seg_end = segments[idx].get("end", seg_start + 1)
    seg_duration = max(seg_end - seg_start, 0.1)
    w_duration = seg_duration / max(len(text_words), 1)
    segments[idx]["words"] = [
        {"word": w, "start": seg_start + i * w_duration, "end": seg_start + (i + 1) * w_duration}
        for i, w in enumerate(text_words)
    ]
    rec.segments = list(segments)  # neue Referenz → SQLAlchemy erkennt die Änderung
    rec.text = " ".join(s["text"] for s in segments)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text}
