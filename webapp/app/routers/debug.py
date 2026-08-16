"""TEMPORÄRE Debug-Endpunkte für die Diarize-Diagnose (2026-08-16).

NACH ABSCHLUSS DER DIAGNOSE ENTFERNEN (Datei + main.py-Registrierung)!

Zweck: ohne SSH-Zugang auf die Box die Roh-Antwort des diar-Service und die
diar-Container-Logs abrufen — das fehlende Puzzlestück für den
Longfile-Diarize-Kollaps („Speaker bis ~10 min, danach nicht mehr", 2026-08-16).

Gate: ``POLYSCHNACK_DEBUG_TOKEN`` muss gesetzt sein (sonst 404 für den ganzen
Router); der Request muss das Token als Query-Param ``token`` ODER als Header
``X-Debug-Token`` mitschicken (sonst 403). Kein Token im Repo/Commit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session
from ..diarize import diarize_raw
from ..docker_proxy import DockerProxyError, get_docker_client

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _debug_token() -> str:
    """Token-Quelle: zuerst Env (POLYSCHNACK_DEBUG_TOKEN), sonst Datei.

    Datei-Fallback (temporär): ``<DATA_DIR>/debug_token`` — erlaubt das
    Aktivieren ohne compose.yml-Umbau/Restart (Host: ``echo <token> >
    DATA/poc-data/debug_token``). Wird pro Request gelesen, Änderung wirkt
    sofort; Datei löschen = deaktivieren.
    """
    if settings.POLYSCHNACK_DEBUG_TOKEN:
        return settings.POLYSCHNACK_DEBUG_TOKEN
    token_file = Path(settings.DATA_DIR) / "debug_token"
    try:
        return token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def require_debug_token(request: Request) -> None:
    """404 wenn deaktiviert, 403 bei falschem Token."""
    expected = _debug_token()
    if not expected:
        raise HTTPException(404, "debug endpoints disabled")
    token = request.query_params.get("token") or request.headers.get("X-Debug-Token", "")
    if token != expected:
        raise HTTPException(403, "invalid debug token")


@router.get("/diar/raw", dependencies=[Depends(require_debug_token)])
def debug_diar_raw(
    recording_id: str = Query(..., description="Recording-UID"),
    method: Optional[str] = Query(None, description="pyannote|foxnose|vad-turns|… (Default: Server-Methode)"),
    num_speakers: Optional[int] = Query(None, ge=1, le=8),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Roh-Antwort des diar-Service für ein bestehendes Recording (kein Merge).

    Ruft den CrispASR-Server mit exakt denselben Parametern wie der normale
    Diarize-Pfad auf und liefert die UNVERÄNDERTE Antwort (status_code +
    json) — inklusive HTTP != 200. Damit ist sichtbar, ob der Server selbst
    die Speaker-Segmente nur bis ~10 min liefert oder die Webapp sie verliert.
    """
    rec = get_recording_by_uid(session, recording_id)
    if rec is None:
        raise HTTPException(404, "recording not found")
    if not Path(rec.stored_path).exists():
        raise HTTPException(404, f"audio file missing: {rec.stored_path}")
    try:
        return diarize_raw(rec.stored_path, num_speakers=num_speakers, method=method)
    except Exception as exc:  # DiarizationError und unerwartete Fehler sichtbar machen
        raise HTTPException(502, f"diarize_raw failed: {exc}") from exc


@router.get("/diar/logs", dependencies=[Depends(require_debug_token)])
def debug_diar_logs(lines: int = Query(200, ge=10, le=2000)) -> Dict[str, Any]:
    """Letzte Log-Zeilen des diar-Containers (via docker-proxy, auto-discover).

    Zeigt z. B. ``pyannote_seg_bench: chunked …``, ``warning: diarization
    failed …`` oder Cluster-Debug-Zeilen — ohne SSH-Zugang auf die Box.
    """
    try:
        docker = get_docker_client()
        containers: List[Dict[str, Any]] = docker.list_containers()
    except DockerProxyError as exc:
        raise HTTPException(503, f"docker-proxy: {exc}") from exc
    diar_names = sorted(
        n for c in containers for n in c.get("Names", []) if "diar" in n
    )
    if not diar_names:
        raise HTTPException(404, "no diar container found")
    name = diar_names[0]
    try:
        logs = docker.logs(name, tail=lines)
    except DockerProxyError as exc:
        raise HTTPException(502, f"docker logs: {exc}") from exc
    return {"container": name, "logs": logs[-8000:]}
