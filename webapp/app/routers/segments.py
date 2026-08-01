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

    uid = request.session.get("user_id") if settings.OIDC_ENABLED else None
    ensure_access(session, rec, uid, "write")

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
