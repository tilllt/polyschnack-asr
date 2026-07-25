"""PATCH endpoint for inline segment text editing."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording
from ..db import get_session

router = APIRouter(prefix="/api")


class SegmentUpdate(BaseModel):
    text: str


@router.patch("/recordings/{rid}/segments/{idx}")
def update_segment(
    rid: int,
    idx: int,
    body: SegmentUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Update the text of a single segment in-place."""
    rec = get_recording(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    uid = request.session.get("user_id") if settings.OIDC_ENABLED else None
    if uid is not None and rec.user_id != uid:
        raise HTTPException(status_code=403, detail="not your recording")

    if uid is None and settings.OIDC_ENABLED:
        raise HTTPException(status_code=401, detail="authentication required")

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
