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
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
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
from ..ass_export import render_client
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
    # Change 200 — Video-Export über den optionalen Render-Dienst.
    format: str = "alpha_webm"
    fps: int = 25
    width: Optional[int] = None      # Default: PlayRes des Presets
    height: Optional[int] = None
    background: str = "#101418"      # nur burn_mp4 (Aufnahmen sind oft nur Ton)
    crf: int = 28
    include_audio: bool = True       # nur burn_mp4: Ton der Aufnahme mitnehmen


#: Auflösung aus dem erzeugten ASS lesen — der Render soll genau diese Fläche
#: haben, sonst stimmen Schriftgröße und Position nicht.
_PLAYRES_RE = re.compile(r"^PlayRes([XY]):\s*(\d+)", re.M)


def _play_res(ass_content: str) -> tuple:
    found = {m.group(1): int(m.group(2)) for m in _PLAYRES_RE.finditer(ass_content)}
    return found.get("X", 1920), found.get("Y", 1080)


def _recording_duration_s(rec) -> float:
    """Dauer der Aufnahme: Feld, sonst Ende des letzten Segments, sonst 0."""
    if rec.duration_s and rec.duration_s > 0:
        return float(rec.duration_s)
    ends = [float(s.get("end") or 0) for s in (rec.segments or []) if isinstance(s, dict)]
    return max(ends) if ends else 0.0


#: ``Dialogue: 0,0:00:01.20,…`` — Start, Ende.
_DIALOGUE_RE = re.compile(r"^Dialogue: \d+,(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),", re.M)


def _ass_end_s(ass_content: str) -> float:
    """Ende des letzten Untertitel-Events im ASS (Sekunden)."""
    def _to_s(stamp: str) -> float:
        h, m, rest = stamp.split(":")
        s, cs = rest.split(".")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0

    ends = [_to_s(m.group(2)) for m in _DIALOGUE_RE.finditer(ass_content)]
    return max(ends) if ends else 0.0


def _render_503(detail: str = "") -> HTTPException:
    """Ehrlicher Hinweis statt totem Knopf (Change 193/200)."""
    hint = ("Video-Rendern ist auf dieser Installation nicht aktiviert — "
            "die .ass-Datei lässt sich herunterladen und z. B. mit ffmpeg "
            "selbst einbrennen.")
    if detail:
        hint = f"{hint} (Dienst: {detail})"
    return HTTPException(status_code=503, detail={"error": "render_unavailable", "hint": hint})


def _job_error(exc: "render_client.RenderError") -> HTTPException:
    status = {"not_finished": 409, "expired": 410, "unknown_job": 404}.get(exc.code, 502)
    return HTTPException(status_code=status, detail={"error": exc.code, "detail": exc.detail})


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
    """Preset-Katalog für den Export-Dialog (Name, Beschreibung, Defaults).

    ``render_available`` kommt aus der Health-Antwort des Render-Dienstes —
    nicht aus einer Annahme. Fehlt er, bleibt es False und die GUI zeigt keinen
    Knopf, der nichts tut; ``render_note`` nennt den Grund.
    """
    health = render_client.health()
    formats = list(render_client.formats())
    return {
        "presets": [preset.as_dict() for preset in list_presets()],
        "parameter_specs": parameter_specs(),
        "render_available": bool(formats),
        "render_formats": formats,
        "render_status": health.get("status", "unknown"),
        "render_note": "" if formats else health.get("detail", ""),
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
        result = generate_ass(rec, body.preset, body.params)  # Parameter/Zeiten prüfen
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

    # ---- Change 200: Video-Export über den optionalen Render-Dienst ---------
    formats = {f["id"]: f for f in render_client.formats()}
    if not formats:
        raise _render_503(render_client.health().get("detail", ""))
    if body.format not in formats:
        raise HTTPException(status_code=400, detail={
            "error": "unsupported_format",
            "detail": f"Format '{body.format}' kann diese Installation nicht "
                      f"(verfügbar: {', '.join(sorted(formats))}).",
        })

    duration_s = max(_recording_duration_s(rec), _ass_end_s(result.content))
    if duration_s <= 0:
        raise HTTPException(status_code=409, detail={
            "error": "no_duration",
            "hint": "Die Dauer der Aufnahme ist unbekannt — Video-Export nicht möglich.",
        })

    # Die Fläche des ASS ist maßgeblich: dort sind Schriftgröße und Position
    # definiert. Explizite Angaben im Request stechen sie.
    width, height = _play_res(result.content)
    width = body.width or width
    height = body.height or height

    # burn_mp4: Ton der Aufnahme mitnehmen, wenn die Datei noch da ist.
    media = None
    if body.format == "burn_mp4" and body.include_audio and rec.stored_path:
        audio = Path(rec.stored_path)
        if audio.is_file():
            media = (audio.name, audio.read_bytes(), "application/octet-stream")

    try:
        job = render_client.start(
            ass_bytes=result.content.encode("utf-8"),
            filename=_safe_filename(rec.original_name),
            fmt=body.format,
            duration_s=duration_s,
            width=width,
            height=height,
            fps=body.fps,
            background=body.background,
            crf=body.crf,
            media=media,
        )
    except render_client.RenderUnavailable as exc:
        raise _render_503(exc.detail)
    except render_client.RenderError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.code, "detail": exc.detail})

    return JSONResponse(status_code=202, content={
        **job,
        "duration_s": duration_s,
        "width": width,
        "height": height,
        "format_label": formats[body.format]["label"],
        "audio": bool(media),
    })


@router.get("/recordings/{rid}/export/jobs/{job_id}")
def export_job_status(
    rid: str,
    job_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Zustand + Fortschritt eines Render-Auftrags (Zugriff wie beim Export)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    try:
        return render_client.status(job_id)
    except render_client.RenderUnavailable as exc:
        raise _render_503(exc.detail)
    except render_client.RenderError as exc:
        raise _job_error(exc)


@router.delete("/recordings/{rid}/export/jobs/{job_id}")
def export_job_cancel(
    rid: str,
    job_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Laufenden Render abbrechen (der Dienst gibt die CPU frei)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    try:
        return render_client.cancel(job_id)
    except render_client.RenderUnavailable as exc:
        raise _render_503(exc.detail)
    except render_client.RenderError as exc:
        raise _job_error(exc)


@router.get("/recordings/{rid}/export/jobs/{job_id}/file")
def export_job_file(
    rid: str,
    job_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """Fertige Datei ausliefern — als Strom durchgereicht (ProRes sind groß)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))

    try:
        client, upstream = render_client.open_file(job_id)
    except render_client.RenderUnavailable as exc:
        raise _render_503(exc.detail)
    except render_client.RenderError as exc:
        raise _job_error(exc)

    fallback = _safe_filename(rec.original_name).rsplit(".", 1)[0] + ".bin"
    filename = render_client.filename_from_headers(upstream, fallback)
    media_type = upstream.headers.get("content-type", "application/octet-stream")

    def _chunks():
        try:
            for chunk in upstream.iter_bytes(256 * 1024):
                yield chunk
        finally:
            upstream.close()
            client.close()

    return StreamingResponse(_chunks(), media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    })
