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
    text: str | None = None
    # Feature 2026-08-16: Sprecher-Zuweisung pro Segment (Dropdown) — nur
    # dieses Segment, kein globales Rename. Wörter bleiben unberührt.
    speaker: str | None = None


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

    new_text = body.text.strip() if body.text is not None else None
    new_speaker = body.speaker.strip() if body.speaker is not None else None
    if new_text is None and new_speaker is None:
        raise HTTPException(
            status_code=400, detail="text or speaker must be provided"
        )

    if new_text is not None:
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
    if new_speaker is not None:
        if not new_speaker:
            raise HTTPException(status_code=400, detail="speaker must not be empty")
        # Nur Sprecher-Zuweisung: Wörter/Timestamps bleiben unangetastet.
        if new_speaker == "_none":
            segments[idx].pop("speaker", None)
        else:
            segments[idx]["speaker"] = new_speaker
    rec.segments = list(segments)  # neue Referenz → SQLAlchemy erkennt die Änderung
    rec.text = " ".join(s["text"] for s in segments)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text}


class SegmentListUpdate(BaseModel):
    """Komplette Segmentliste (Feature 2026-08-15: Segmentlängen).

    Vom Frontend nach Re-Segmentierung (frei wählbare Dauer) oder
    manuell verschobenen Grenzen (draggable Timecode-Marker) gesendet.
    Die Wörter bleiben erhalten — nur start/end/text/Speaker dürfen
    abweichen. Persistiert wird die Liste; der Export (SRT/VTT) und die
    Preview nutzen damit dieselben Grenzen.
    """

    segments: list[dict[str, Any]]


@router.put("/recordings/{rid}/segments")
def replace_segments(
    rid: str,
    body: SegmentListUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Ersetzt die komplette Segmentliste einer fertigen Aufnahme.

    Auth + Zugriff wie beim Segment-Edit (write). Der Gesamt-Text wird
    aus den Segment-Texten neu zusammengesetzt. Voraussetzung: mindestens
    ein Segment; jedes Segment braucht start/end/text. Wörter sind
    optional, bleiben aber für Karaoke + Wort-für-Wort-Verschiebung
    erhalten.
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

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    segs = body.segments
    if not segs:
        raise HTTPException(status_code=400, detail="segments must not be empty")
    for i, s in enumerate(segs):
        if "start" not in s or "end" not in s:
            raise HTTPException(
                status_code=400, detail=f"segment {i} missing start/end"
            )
        if not str(s.get("text") or "").strip():
            raise HTTPException(status_code=400, detail=f"segment {i} empty text")

    # Tiefe Kopie → SQLAlchemy erkennt die Zuweisung als Änderung.
    import json as _json

    stored = _json.loads(_json.dumps(segs))
    rec.segments = stored
    rec.text = " ".join(str(s["text"]).strip() for s in stored)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text}
