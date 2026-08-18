"""Recovery (2026-08-15) — verwaiste Aufnahmen wieder sichtbar machen.

Hintergrund: Beim Upload wird zuerst die Datei auf die Platte geschrieben,
dann der DB-Commit gemacht. Stirbt der Prozess dazwischen (OOM, Crash,
Netz-Abbruch im falschen Moment), bleibt die Datei als Waise im AUDIO_DIR
zurück: kein Recording-Eintrag → in der App unsichtbar → „im Nirvana
verschwunden".

Dieser Router:
  GET  /api/recovery/scan     → verwaiste Dateien auflisten (Admin)
  POST /api/recovery/restore  → Waise als Recording wiederherstellen (Admin)

Der Restore legt die Recording-Row NICHT mit der Original-Datei an (die
Waise bleibt liegen), sondern kopiert sie auf einen frischen Pfad — so
bleibt die Datenbank konsistent, auch wenn die Waise später vom
Orphan-Sweep aufgeräumt wird. Status = 'uploaded' → die App zeigt die
Aufnahme wieder und kann sie transkribieren.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..crud import create_recording
from ..db import get_session
from ..models import Recording

router = APIRouter(prefix="/api/recovery")


def _require_admin(request: Request) -> None:
    """Admin-only: verwaiste Dateien sind potenziell sensible Audiodaten."""
    from ..config import settings as _s

    if not _s.OIDC_ENABLED:
        return  # ohne OIDC gibt es keine Rollen — Recovery ist dann lokal/DEV
    if not bool(request.session.get("is_admin")):
        raise HTTPException(status_code=403, detail="admin required")


def _collect_referenced(session: Session) -> set:
    paths: set = set()
    for rec in session.exec(select(Recording)).all():
        if rec.stored_path:
            paths.add(str(rec.stored_path))
        if getattr(rec, "preview_path", None):
            paths.add(str(rec.preview_path))
    return paths


def scan_orphans(audio_dir: Path, referenced: set, min_age_s: int = 60) -> List[dict]:
    """Verwaiste Audiodateien finden — keine DB-Referenz, älter als min_age_s.

    min_age_s schützt laufende Uploads (Datei wird VOR dem DB-Commit
    geschrieben — eine 10 s alte Datei ist evtl. gerade im Commit).
    """
    now = time.time()
    out: List[dict] = []
    if not audio_dir.is_dir():
        return out
    with os.scandir(audio_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            if str(entry.path) in referenced or entry.name in referenced:
                continue
            try:
                st = entry.stat()
                age = now - st.st_mtime
            except OSError:
                continue
            if age < min_age_s:
                continue
            out.append({
                "filename": entry.name,
                "size_bytes": st.st_size,
                "age_s": int(age),
                "path": entry.path,
            })
    out.sort(key=lambda d: d["age_s"], reverse=True)  # älteste zuerst
    return out


@router.get("/scan")
def recovery_scan(request: Request, session: Session = Depends(get_session)) -> dict:
    """Alle verwaisten Audiodateien im AUDIO_DIR auflisten (Admin)."""
    _require_admin(request)
    referenced = _collect_referenced(session)
    orphans = scan_orphans(settings.AUDIO_DIR, referenced)
    return {"count": len(orphans), "orphans": orphans}


class RestoreBody(BaseModel):
    filename: str


@router.post("/restore")
def recovery_restore(body: RestoreBody, request: Request,
                     session: Session = Depends(get_session)) -> dict:
    """Verwaiste Datei als sichtbares Recording wiederherstellen (Admin)."""
    _require_admin(request)
    # Pfad-Traversal abwehren: nur Dateiname, keine Pfad-Separatoren
    if "/" in body.filename or "\\" in body.filename or ".." in body.filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    src = settings.AUDIO_DIR / body.filename
    if not src.is_file():
        raise HTTPException(status_code=404, detail="orphan file not found")

    # Waisen-Konsistenz: falls inzwischen doch referenziert (Race), ablehnen
    referenced = _collect_referenced(session)
    if str(src) in referenced or src.name in referenced:
        raise HTTPException(status_code=409, detail="file is already referenced")

    raw = src.read_bytes()
    content_hash = hashlib.blake2b(raw, digest_size=16).hexdigest()
    ext = src.suffix.lower() or ".bin"
    import uuid

    new_path = settings.AUDIO_DIR / f"{uuid.uuid4().hex}{ext}"
    new_path.write_bytes(raw)

    rec = create_recording(
        session,
        original_name=f"[wiederhergestellt] {src.name}",
        stored_path=str(new_path),
        mime="audio/wav" if ext == ".wav" else "application/octet-stream",
        size_bytes=len(raw),
        content_hash=content_hash,
        user_id=None,  # anonym — gehört niemandem, aber ist sichtbar
        # Change 014: Owner-Fallback — der Admin, der den Restore auslöst,
        # kann die Recording damit wieder löschen (user_id=None → sonst nur read).
        owner_user_id=None,
    )
    # Peaks im Hintergrund nachziehen (wie beim normalen Upload)
    try:
        from .recordings import _schedule_peaks

        _schedule_peaks(rec.id)
    except Exception:
        pass
    return {"restored": rec.uid, "original_name": rec.original_name}
