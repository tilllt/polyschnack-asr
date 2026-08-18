"""Self-Healing: Orphan-Audio-Dateien aufräumen (2026-08-15).

Dateien im AUDIO_DIR, auf die KEIN Recording.stored_path / preview_path
zeigt, sind Waisen (z.B. nach Crash zwischen File-Write und DB-Commit,
oder nach manuellem DB-Eingriff). Sie fressen Platte und tauchen nirgends
auf. Der Sweep löscht nur Dateien, die älter als *min_age_s* sind — so
werden laufende Uploads (Datei wird VOR dem DB-Commit geschrieben) nie
erfasst, und ein gleichzeitiger Re-Transcribe-Crop (schreibt neue Datei)
bleibt unangetastet.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Set

from sqlmodel import Session, select

from .models import Recording

log = logging.getLogger(__name__)

#: Dateien jünger als diese Schwelle werden NIE angefasst (laufender Upload).
MIN_ORPHAN_AGE_S = 3600  # 1 h


def collect_referenced_paths(session: Session) -> Set[str]:
    """Alle Dateipfade, die aktuell von Recording-Rows referenziert werden."""
    paths: Set[str] = set()
    for rec in session.exec(select(Recording)).all():
        if rec.stored_path:
            paths.add(rec.stored_path)
        if getattr(rec, "preview_path", None):
            paths.add(rec.preview_path)  # type: ignore[arg-type]
    return paths


def _is_referenced(name: str, referenced: Set[str], audio_dir: Path) -> bool:
    """True, wenn *name* (flacher Dateiname) von einer Recording referenziert ist.

    Referenzen können absolut (stored_path) oder relativ (nur Dateiname)
    gespeichert sein — beide Formen werden geprüft.
    """
    if name in referenced:
        return True
    abs_path = str(audio_dir / name)
    return abs_path in referenced


def sweep_orphan_files(
    audio_dir: Path,
    referenced: Set[str],
    min_age_s: int = MIN_ORPHAN_AGE_S,
    dry_run: bool = False,
) -> List[str]:
    """Lösche un-referenzierte Dateien in *audio_dir* (nicht rekursiv).

    Returns the list of deleted (or would-be-deleted) file names.
    """
    now = time.time()
    removed: List[str] = []
    if not audio_dir.is_dir():
        return removed
    with os.scandir(audio_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            if _is_referenced(entry.name, referenced, audio_dir):
                continue
            try:
                age = now - entry.stat().st_mtime
            except OSError:
                continue
            if age < min_age_s:
                continue
            if not dry_run:
                try:
                    os.unlink(entry.path)
                except OSError as exc:
                    log.warning("orphan sweep: %s nicht löschbar: %s", entry.name, exc)
                    continue
            removed.append(entry.name)
    if removed:
        log.info(
            "orphan sweep (%s): %d Datei(en) entfernt",
            "dry-run" if dry_run else "ausgeführt",
            len(removed),
        )
    return removed
