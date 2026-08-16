"""Account-Exfiltration: Eigene Daten als ZIP herunterladen (2026-08-15).

GET /api/account/export — eingeloggter User lädt ein ZIP mit ALLEN eigenen
Recordings. Struktur: 1 Transkription = 1 Ordner:

    <uid>-<original_name ohne Endung>/
        audio/<original_name>          # Original-Upload (falls vorhanden)
        transkription.json             # PolySchnack-JSON-Format (schema v1)

Nur EIGENE Recordings (user_id == aktueller User), keine Shares. Fehlt die
Audiodatei (Self-Healing), wird statt eines Crashes eine
``AUDIO_FEHLT.txt``-Notiz in den Ordner gelegt — der Export bleibt nutzbar.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_authenticated
from ..models import Recording

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(require_authenticated)])

_EXPORT_SCHEMA = "polyschnack-transcription-v1"
_AUDIO_MISSING_NOTE = (
    "Die Audiodatei dieser Aufnahme fehlt auf dem Server (gelöscht oder\n"
    "nicht mehr vorhanden). Die Transkription ist trotzdem vollständig\n"
    "exportiert — diese Notiz ersetzt das Audio in diesem Ordner.\n"
)


def _sanitize(name: str) -> str:
    """Dateinamen für ZIP-Einträge sicher machen (kein Pfad-Traversal)."""
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name).strip()
    return cleaned or "recording"


def _recording_json(rec: Recording) -> Dict[str, Any]:
    """PolySchnack-JSON-Format v1 für EINE Transkription."""
    return {
        "schema": _EXPORT_SCHEMA,
        "original_name": rec.original_name,
        "uid": rec.uid,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "language": rec.language,
        "duration_s": rec.duration_s,
        "status": rec.status,
        "backend": rec.backend,
        "enable_vad": rec.enable_vad,
        "enable_diarize": rec.enable_diarize,
        "text": rec.text,
        "segments": rec.segments or [],
    }


def _zip_recordings(recs: List[Recording], zip_path: Path) -> int:
    """Schreibe alle *recs* als ZIP nach *zip_path*; returns Anzahl Ordner."""
    n = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for rec in recs:
            folder = f"{rec.uid}-{_sanitize(Path(rec.original_name).stem)}"
            zf.writestr(
                f"{folder}/transkription.json",
                json.dumps(_recording_json(rec), ensure_ascii=False, indent=2),
            )
            audio = Path(rec.stored_path)
            if audio.is_file():
                zf.write(audio, arcname=f"{folder}/audio/{_sanitize(audio.name)}")
            else:
                # Self-Healing: kein Crash, kein stiller Verlust — Notiz statt Audio.
                zf.writestr(f"{folder}/AUDIO_FEHLT.txt", _AUDIO_MISSING_NOTE)
            n += 1
    return n


def _own_recordings(session: Session, user_id: int) -> List[Recording]:
    """Nur eigene Recordings (KEINE Shares) — inkl. nicht fertiger/fehlgeschlagener."""
    return list(
        session.exec(select(Recording).where(Recording.user_id == user_id)).all()
    )


def _current_user_id(request: Request, session: Session) -> Optional[int]:
    from ..identity import current_identity

    ident = current_identity(request, session)
    return ident.user.id if ident and ident.user else None


@router.get("/account/export")
def export_account(
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Alle eigenen Daten als ZIP (Original-Uploads + Transkriptionen)."""
    uid = _current_user_id(request, session)
    if uid is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="login required")

    recs = _own_recordings(session, uid)
    if not recs:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="keine eigenen Aufnahmen")

    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="ps-export-")
    import os as _os

    _os.close(fd)  # FD sofort schließen — zipfile öffnet selbst
    try:
        n = _zip_recordings(recs, Path(tmp_path))
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        fname = f"polyschnack-export-{stamp}.zip"
        log.info("account export: user_id=%s, %d ordner → %s", uid, n, fname)
        resp = FileResponse(
            tmp_path,
            media_type="application/zip",
            filename=fname,
            headers={"Cache-Control": "no-store"},
        )
        # Datei nach dem Stream aufräumen (FileResponse löscht nicht selbst).
        from starlette.background import BackgroundTask

        resp.background = BackgroundTask(_unlink_after, Path(tmp_path))
        return resp
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _unlink_after(path: Path):
    def _cleanup() -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass

    return _cleanup
