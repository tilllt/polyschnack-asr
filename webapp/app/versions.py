"""Versions-Snapshots: anlegen, auflisten, diffen (Task A6/A7)."""
from __future__ import annotations

import datetime as dt
import difflib
from typing import Any, List, Optional

from sqlmodel import Session, func, select

from .models import TranscriptVersion


def snapshot(
    session: Session, rec, kind: str, user_id: Optional[int] = None
) -> Optional[TranscriptVersion]:
    """Voll-Snapshot von *rec* als neue Version anlegen (nur bei Ergebnissen)."""
    if not (rec.text or rec.segments):
        return None
    max_no = session.exec(
        select(func.max(TranscriptVersion.version_no)).where(
            TranscriptVersion.rec_id == rec.id
        )
    ).first() or 0
    v = TranscriptVersion(
        rec_id=rec.id,
        version_no=int(max_no) + 1,
        kind=kind,
        text=rec.text,
        segments=list(rec.segments) if rec.segments else None,
        backend=rec.backend or "",
        language=rec.language,
        created_by_user_id=user_id,
    )
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def list_versions(
    session: Session, rec_id: int, since: Optional[dt.datetime] = None
) -> List[TranscriptVersion]:
    """Versionen einer Aufnahme auflisten.

    ``since`` (Anon-Share-Link): Versionen VOR dem Share-Zeitpunkt sind für
    den Link-Empfänger unsichtbar („discarded") — nur neuere werden geliefert.
    """
    stmt = (
        select(TranscriptVersion)
        .where(TranscriptVersion.rec_id == rec_id)
    )
    if since is not None:
        stmt = stmt.where(TranscriptVersion.created_at >= since)
    stmt = stmt.order_by(TranscriptVersion.version_no.asc())
    return list(session.exec(stmt).all())


def get_diff(a: TranscriptVersion, b: TranscriptVersion) -> List[dict]:
    """Zeilen-Diff a → b: [{type: same|add|del, text}]."""
    a_lines = (a.text or "").splitlines()
    b_lines = (b.text or "").splitlines()
    out: List[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a_lines, b_lines
    ).get_opcodes():
        if tag == "equal":
            out += [{"type": "same", "text": l} for l in a_lines[i1:i2]]
        elif tag == "delete":
            out += [{"type": "del", "text": l} for l in a_lines[i1:i2]]
        elif tag == "insert":
            out += [{"type": "add", "text": l} for l in b_lines[j1:j2]]
        else:  # replace
            out += [{"type": "del", "text": l} for l in a_lines[i1:i2]]
            out += [{"type": "add", "text": l} for l in b_lines[j1:j2]]
    return out
