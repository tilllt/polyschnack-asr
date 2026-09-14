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
         limit: Optional[int] = None) -> Dict[str, Any]:
    """Dry-Run: was würde die Migration ändern? (schreibt nichts)"""
    report: Dict[str, Any] = {
        "migration": MIGRATION,
        "dry_run": True,
        "recordings": [],
        "recordings_actionable": 0,
        "segments_changed": 0,
        "overlaps_resolved": 0,
    }
    for rec in _candidates(session, uid, limit):
        segs = _deep(rec.segments or [])
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
          user_id: Optional[int] = None) -> Dict[str, Any]:
    """Migration ausführen: Grenzen auf Wortkanten ziehen + Version-Snapshot.

    Idempotent (ein zweiter Lauf findet nichts mehr). Text und Wortlisten
    bleiben unangetastet; Segmente ohne Wörter werden nicht angefasst.
    """
    report: Dict[str, Any] = {
        "migration": MIGRATION,
        "dry_run": False,
        "recordings": [],
        "written": 0,
        "segments_changed": 0,
        "overlaps_resolved": 0,
    }
    for rec in _candidates(session, uid, limit):
        before = _deep(rec.segments or [])
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
