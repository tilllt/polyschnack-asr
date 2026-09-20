"""Versions-Snapshots: anlegen, auflisten, diffen (Task A6/A7)."""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import logging
from typing import Any, List, Optional

from sqlmodel import Session, func, select

from .models import TranscriptVersion

log = logging.getLogger(__name__)

#: Change 217: Schlüssel, die den INHALT eines Segments ausmachen.
#: Bewusst NICHT enthalten: ``id`` und andere reine Anzeige-/Buchhaltungsfelder
#: — sie ändern sich, ohne dass sich die Transkription ändert.
_SEGMENT_INHALT_KEYS = ("text", "speaker", "start", "end", "words")


def _round3(value: Any) -> Any:
    """Zahl auf Millisekunden runden (Float-Rauschen ist keine Textänderung)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return str(value)
    return value


def _norm_words(words: Any) -> List[dict]:
    out: List[dict] = []
    for w in words or []:
        if not isinstance(w, dict):
            out.append({"word": str(w)})
            continue
        out.append(
            {
                "word": str(w.get("word") or ""),
                "start": _round3(w.get("start")),
                "end": _round3(w.get("end")),
            }
        )
    return out


def _norm_segments(segments: Any) -> List[dict]:
    out: List[dict] = []
    for s in segments or []:
        if not isinstance(s, dict):
            continue
        norm: dict = {}
        for key in _SEGMENT_INHALT_KEYS:
            if key not in s:
                continue
            value = s[key]
            if key == "words":
                norm[key] = _norm_words(value)
            elif key in ("start", "end"):
                norm[key] = _round3(value)
            elif key == "speaker":
                norm[key] = None if value is None else str(value)
            else:
                norm[key] = str(value)
        out.append(norm)
    return out


def content_fingerprint(text: Any, segments: Any) -> str:
    """Change 217: Fingerabdruck des INHALTS einer Transkription.

    Verglichen wird der Inhalt — der Gesamt-Text, die Segmenttexte in ihrer
    REIHENFOLGE, Sprecher, Segment-Grenzen und Wortlisten (auf Millisekunden
    gerundet). Bewusst NICHT verglichen werden die Buchhaltungs-Zeitstempel
    (``updated_at``/``created_at``): die werden bei JEDEM Schreiben neu gesetzt
    und sagen nichts darüber aus, ob sich der Text geändert hat. Genau daraus
    entstand die Versionsflut (Aufnahme mit 323 Versionen, viele davon
    inhaltlich identisch, teils 16 s auseinander).

    Gleicher Fingerabdruck = kein Inhaltsunterschied = keine neue Version und
    kein unnötiger Schreibvorgang. Der Fingerabdruck ist außerdem die einzige
    Definition von „gleicher Inhalt" — Client (Texte in Reihenfolge) und
    Server (voller Inhalt) benutzen dieselbe Idee, der Server ist maßgeblich.
    """
    payload = {
        "text": "" if text is None else str(text),
        "segments": _norm_segments(segments),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _latest_version(session: Session, rec_id: int) -> Optional[TranscriptVersion]:
    """Jüngste vorhandene Version (höchste ``version_no``) — oder None."""
    max_no = session.exec(
        select(func.max(TranscriptVersion.version_no)).where(
            TranscriptVersion.rec_id == rec_id
        )
    ).first()
    if not max_no:
        return None
    return session.exec(
        select(TranscriptVersion).where(
            TranscriptVersion.rec_id == rec_id,
            TranscriptVersion.version_no == int(max_no),
        )
    ).first()


def snapshot(
    session: Session, rec, kind: str, user_id: Optional[int] = None
) -> Optional[TranscriptVersion]:
    """Voll-Snapshot von *rec* als neue Version anlegen (nur bei Ergebnissen).

    Change 217: Eine Version entsteht NUR, wenn sich der Inhalt wirklich
    geändert hat. Trägt die jüngste vorhandene Version denselben
    Inhalts-Fingerabdruck (Text + Segmente, siehe ``content_fingerprint``),
    wird KEINE Version angelegt und ``None`` zurückgegeben — der Aufrufer
    erkennt daran ehrlich, dass nichts angelegt wurde. Bestehende Versionen
    werden dabei weder gelöscht noch umgeschrieben (ausdrückliche Vorgabe).
    Der Vergleich liegt hier — an der einzigen Stelle, an der Versionen
    entstehen — damit ALLE Schreibpfade (Autosave, Edit-Mode-Ende, Grenz-Drag,
    Undo/Redo, Restore, Pipeline) gleichermaßen geschützt sind.
    """
    if not (rec.text or rec.segments):
        return None
    fp = content_fingerprint(rec.text, rec.segments)
    last = _latest_version(session, rec.id)
    if last is not None and content_fingerprint(last.text, last.segments) == fp:
        log.info(
            "Change 217: keine neue Version für Aufnahme %s — Inhalt identisch "
            "mit Version %s (Kind %s wird nicht dupliziert)",
            rec.id, last.version_no, last.kind,
        )
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
