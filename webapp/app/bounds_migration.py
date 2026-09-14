"""Change 187 — Migration: Segmentgrenzen aus den Wortlisten ableiten.

Hintergrund: Vor Change 187 waren Segmentgrenzen freie Zeitwerte. Passten sie
nicht zu den Wörtern (Drift, Überlappungen), scheiterte das Re-Align: die
Wortzuordnung lief über Zeitfenster, `reconcile_words_to_text` fiel auf eine
Gleichverteilung zurück und der Lauf endete als „ohne Effekt".

Diese Migration zieht die Grenzen einmalig auf die Wortkanten
(`app.word_anchors`), löst Überlappungen auf und schreibt je Recording einen
Versions-Snapshot (`kind="edit"`) — Text und Wortlisten bleiben unverändert.

- `plan(session, uid=None, limit=None)` — Dry-Run-Bericht (read-only).
- `apply(session, uid=None, limit=None, user_id=None)` — schreibt die Grenzen.

Beide Funktionen sind die eine Quelle der Wahrheit für Admin-Endpoint
(`/api/admin/bounds-from-words`) und CLI
(`scripts/bounds_from_words_migration.py`).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from . import versions
from .models import Recording
from .word_anchors import enforce_word_anchored_bounds, plan_bound_correction

#: Migrations-Kennzeichnung im Bericht (Nachvollziehbarkeit).
MIGRATION = "change187-bounds-from-words"

#: Ab so vielen Wörtern wird die Gleichverteilungs-Prüfung angewendet.
_MIN_WORDS_FOR_REAL_CHECK = 5


def words_look_real(segments: List[Dict[str, Any]]) -> bool:
    """Sind die Wortzeiten echt (Aligner/ASR) oder nur ein Platzhalter-Raster?

    Prod-Befund 2026-09-14 (Dry-Run über 93 Recordings): Bei Aufnahmen mit
    Backend-Platzhalter-Timings (Gleichverteilung) würde die Wortkanten-Regel
    Grenzen um BIS ZU 776 s verschieben — inhaltlich zerstörerisch. Deshalb
    gilt die Migration nur für Segmente mit echten Wortzeiten:

    - Platzhalter = innerhalb des Segments nur 1–2 verschiedene
      Wort-zu-Wort-Abstände (`_distribute_words`) UND Wortspanne deutlich
      kleiner als die Segmentdauer.
    - Ein Recording gilt als „echt", wenn mindestens die Hälfte seiner
      Segmente mit Wörtern echte Zeiten hat.
    """
    real = 0
    total = 0
    for seg in segments:
        words = seg.get("words") or []
        if len(words) < _MIN_WORDS_FOR_REAL_CHECK:
            continue
        total += 1
        starts = [w.get("start") for w in words if isinstance(w.get("start"), (int, float))]
        if len(starts) < _MIN_WORDS_FOR_REAL_CHECK:
            continue
        steps = {round(starts[i + 1] - starts[i], 2) for i in range(len(starts) - 1)}
        raster = len(steps) <= 2  # _distribute_words-Signatur (Gleichverteilung)
        if not raster:
            real += 1
    if total == 0:
        return False
    return real * 2 >= total


def _candidates(session: Session, uid: Optional[str], limit: Optional[int]) -> List[Recording]:
    stmt = select(Recording)
    if uid:
        stmt = stmt.where(Recording.uid == uid)
    rows = list(session.exec(stmt).all())
    out = [r for r in rows if r.segments]
    out.sort(key=lambda r: r.id or 0)
    return out[:limit] if limit else out


def _deep(obj: Any) -> Any:
    """JSON-Deepcopy für Segmentlisten (SQLAlchemy würde sonst Aliasse teilen)."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def plan(session: Session, uid: Optional[str] = None,
         limit: Optional[int] = None,
         include_placeholders: bool = False) -> Dict[str, Any]:
    """Dry-Run: was würde die Migration ändern? (schreibt nichts)

    ``include_placeholders=False`` (Default) überspringt Aufnahmen, deren
    Wortzeiten nur ein Platzhalter-Raster sind (siehe ``words_look_real``) —
    dort würde die Wortkanten-Regel Grenzen um Minuten verschieben.
    """
    report: Dict[str, Any] = {
        "migration": MIGRATION,
        "dry_run": True,
        "recordings": [],
        "recordings_actionable": 0,
        "recordings_skipped_placeholder": 0,
        "segments_changed": 0,
        "overlaps_resolved": 0,
    }
    for rec in _candidates(session, uid, limit):
        segs = _deep(rec.segments or [])
        if not include_placeholders and not words_look_real(segs):
            report["recordings_skipped_placeholder"] += 1
            continue
        r = plan_bound_correction(segs)
        if not r["actionable"]:
            continue
        entry = {
            "id": rec.id,
            "uid": rec.uid,
            "title": rec.title or rec.original_name,
            "segments": r["segments"],
            "segments_changed": len(r["bounds_changed"]),
            "overlaps": r["overlaps"],
            "shifted": r["shifted"],
            "max_end_delta_s": r["max_end_delta_s"],
            "max_start_delta_s": r["max_start_delta_s"],
            "without_words": r["without_words"],
            "changes": r["bounds_changed"],
        }
        report["recordings"].append(entry)
        report["recordings_actionable"] += 1
        report["segments_changed"] += entry["segments_changed"]
        report["overlaps_resolved"] += len(entry["overlaps"])
    return report


def apply(session: Session, uid: Optional[str] = None, limit: Optional[int] = None,
          user_id: Optional[int] = None,
          include_placeholders: bool = False) -> Dict[str, Any]:
    """Migration ausführen: Grenzen auf Wortkanten ziehen + Version-Snapshot.

    Idempotent (ein zweiter Lauf findet nichts mehr). Text und Wortlisten
    bleiben unangetastet; Segmente ohne Wörter werden nicht angefasst.
    """
    report: Dict[str, Any] = {
        "migration": MIGRATION,
        "dry_run": False,
        "recordings": [],
        "written": 0,
        "recordings_skipped_placeholder": 0,
        "segments_changed": 0,
        "overlaps_resolved": 0,
    }
    for rec in _candidates(session, uid, limit):
        before = _deep(rec.segments or [])
        if not include_placeholders and not words_look_real(before):
            report["recordings_skipped_placeholder"] += 1
            continue
        r = plan_bound_correction(before)
        if not r["actionable"]:
            continue
        after = enforce_word_anchored_bounds(_deep(before))
        # Ehrlichkeits-Check: nur Grenzen dürfen sich ändern.
        for b, a in zip(before, after):
            if (b.get("text") or "") != (a.get("text") or ""):
                raise RuntimeError(f"Migration würde Text ändern (rec {rec.id}) — abgebrochen")
            if len(b.get("words") or []) != len(a.get("words") or []):
                raise RuntimeError(f"Migration würde Wörter verlieren (rec {rec.id}) — abgebrochen")
        versions.snapshot(session, rec, "edit", user_id=user_id)
        rec.segments = after
        session.add(rec)
        session.commit()
        session.refresh(rec)
        report["recordings"].append({
            "id": rec.id,
            "uid": rec.uid,
            "title": rec.title or rec.original_name,
            "segments_changed": len(r["bounds_changed"]),
            "overlaps_resolved": len(r["overlaps"]),
            "max_end_delta_s": r["max_end_delta_s"],
            "changes": r["bounds_changed"],
        })
        report["written"] += 1
        report["segments_changed"] += len(r["bounds_changed"])
        report["overlaps_resolved"] += len(r["overlaps"])
    return report
