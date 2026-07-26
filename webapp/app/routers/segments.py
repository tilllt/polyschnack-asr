"""PATCH endpoint for inline segment text editing."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session

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
    if uid is not None and rec.user_id != uid:
        raise HTTPException(status_code=403, detail="not your recording")

    # Anonymous users may only edit public (shared-space) recordings
    if uid is None and rec.user_id is not None:
        raise HTTPException(status_code=403, detail="cannot edit another user's recording")

    segments = rec.segments or []
    if idx < 0 or idx >= len(segments):
        raise HTTPException(status_code=404, detail="segment not found")

    new_text = body.text.strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    segments[idx]["text"] = new_text
    rec.segments = segments
    rec.text = " ".join(s["text"] for s in segments)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    return {"segments": rec.segments, "text": rec.text}
