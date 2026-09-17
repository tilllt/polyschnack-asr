"""Caption-Export-API (Change 193): Preset-Katalog + ASS-Download.

Endpunkte:

* ``GET  /api/export/presets`` — Preset-Katalog + Parameter-Schema.
* ``GET  /api/recordings/{rid}/export/ass`` — ``.ass``-Datei (Wort-Timings).
* ``POST /api/recordings/{rid}/export`` — Video brennen (Render-Dienst).

Der Render-Dienst (``ps-render``, Phase 4) ist NICHT Teil des Kerns: fehlt er,
antwortet ``POST /export`` mit 503 ``render_unavailable`` und verweist auf den
ASS-Download. Der Kern bleibt damit ohne ffmpeg-Render-Abhängigkeit.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session

from ..ass_export import (
    AssTemplateError,
    NoWordTimestamps,
    ParamError,
    PresetNotFound,
    generate_ass,
    list_presets,
    parameter_specs,
)
from ..crud import get_recording_by_uid
from ..db import get_session
from ..permissions import ensure_access

router = APIRouter(prefix="/api")

#: ASS ist Text; es gibt keine registrierte IANA-Typisierung. Die SPA liest die
#: Datei per fetch (nicht über einen <a href>), deshalb ist der Typ nur für
#: fremde Clients relevant.
ASS_MEDIA_TYPE = "text/plain; charset=utf-8"


def _current_user(request: Request, session=None) -> Optional[int]:
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _key_cap(request: Request, session=None) -> Optional[str]:
    from ..identity import current_identity

    return current_identity(request, session).key_level


class ExportRequest(BaseModel):
    """Body für ``POST /api/recordings/{rid}/export``."""

    preset: str = "highlight"
    params: Dict[str, Any] = {}
    mode: str = "render"  # "render" | "ass"


def _parse_params(raw: Optional[str]) -> Dict[str, Any]:
    """``params``-Query (JSON-Objekt) lesen — kaputtes JSON ist ein 400."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_params",
            "detail": f"params ist kein gültiges JSON: {exc.msg}",
        })
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail={
            "error": "invalid_params",
            "detail": "params muss ein JSON-Objekt sein",
        })
    return data


def _safe_filename(rec_original_name: Optional[str]) -> str:
    """Dateiname für den Content-Disposition-Header (keine Header-Injektion)."""
    stem = Path(rec_original_name or "captions").stem or "captions"
    cleaned = "".join(ch for ch in stem if ch.isalnum() or ch in " ._-").strip()
    return f"{cleaned or 'captions'}.ass"


@router.get("/export/presets")
def export_presets() -> dict:
    """Preset-Katalog für den Export-Dialog (Name, Beschreibung, Defaults)."""
    return {
        "presets": [preset.as_dict() for preset in list_presets()],
        "parameter_specs": parameter_specs(),
        # Phase 4: erst wenn der optionale ps-render-Container läuft.
        "render_available": False,
    }


@router.get("/recordings/{rid}/export/ass")
def export_ass(
    rid: str,
    request: Request,
    preset: str = Query("highlight"),
    params: Optional[str] = Query(None),
    session: Session = Depends(get_session),
) -> Response:
    """Untertitel als ``.ass``-Datei (Wort-Timings des Recordings erforderlich)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))

    if rec.status != "done":
        raise HTTPException(status_code=409, detail={
            "error": "not_transcribed",
            "hint": "Die Aufnahme ist noch nicht transkribiert.",
        })

    overrides = _parse_params(params)
    try:
        result = generate_ass(rec, preset, overrides)
    except PresetNotFound:
        raise HTTPException(status_code=404, detail={
            "error": "unknown_preset",
            "detail": f"Preset '{preset}' existiert nicht",
        })
    except ParamError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_params", "detail": str(exc),
        })
    except NoWordTimestamps:
        raise HTTPException(status_code=409, detail={
            "error": "no_word_timestamps",
            "hint": "Für den Untertitel-Export werden Wort-Zeiten gebraucht — "
                    "bitte zuerst ausrichten (Re-align).",
        })
    except AssTemplateError as exc:
        raise HTTPException(status_code=500, detail={
            "error": "template_error", "detail": str(exc),
        })

    return Response(
        content=result.content.encode("utf-8"),
        media_type=ASS_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_filename(rec.original_name)}"',
            # Die SPA liest diese Header und zeigt Hinweise (z. B. „Wortzeiten
            # sind mechanisch verteilt") — statt sie still zu verschlucken.
            "X-Polyschnack-Preset": result.preset,
            "X-Polyschnack-Timing": result.timing,
            "X-Polyschnack-Words": str(result.words),
            "X-Polyschnack-Lines": str(result.lines),
            "X-Polyschnack-Warnings": ",".join(result.warnings),
            "Access-Control-Expose-Headers": (
                "Content-Disposition, X-Polyschnack-Preset, "
                "X-Polyschnack-Timing, X-Polyschnack-Words, "
                "X-Polyschnack-Lines, X-Polyschnack-Warnings"
            ),
        },
    )


@router.post("/recordings/{rid}/export")
def export_recording(
    rid: str,
    body: ExportRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """Caption-Video rendern — nur mit konfiguriertem Render-Dienst (Phase 4)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))

    if body.mode not in {"render", "ass"}:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_mode", "detail": "mode muss 'render' oder 'ass' sein",
        })
    try:
        generate_ass(rec, body.preset, body.params)  # Parameter/Zeiten prüfen
    except PresetNotFound:
        raise HTTPException(status_code=404, detail={
            "error": "unknown_preset", "detail": f"Preset '{body.preset}' existiert nicht",
        })
    except ParamError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_params", "detail": str(exc),
        })
    except NoWordTimestamps:
        raise HTTPException(status_code=409, detail={
            "error": "no_word_timestamps",
            "hint": "Für den Untertitel-Export werden Wort-Zeiten gebraucht.",
        })
    except AssTemplateError as exc:
        raise HTTPException(status_code=500, detail={
            "error": "template_error", "detail": str(exc),
        })

    if body.mode == "ass":
        raise HTTPException(status_code=400, detail={
            "error": "wrong_endpoint",
            "detail": "Für den ASS-Download bitte GET …/export/ass verwenden",
        })

    # Kein Render-Dienst konfiguriert/deployt (Compose-Profil "render").
    raise HTTPException(status_code=503, detail={
        "error": "render_unavailable",
        "hint": "Video-Rendern ist auf dieser Installation nicht aktiviert — "
                "die .ass-Datei lässt sich herunterladen und z. B. mit "
                "ffmpeg selbst einbrennen.",
    })
