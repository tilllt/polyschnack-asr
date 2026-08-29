"""APIRouter for /api/recordings and /api/stats.

Each endpoint is thin: parse the incoming request, delegate to ``crud`` or
``service``, then shape the outgoing response dict.  No raw SQL here.
"""
from __future__ import annotations

import datetime as dt
import mimetypes
import time
import uuid
from pathlib import Path
import hashlib
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response, RedirectResponse, JSONResponse
from sqlmodel import Session, select

from ..config import settings
from ..audio_utils import (
    convert_to_wav_16k_mono,
    original_path,
    prepare_storage,
    probe_duration_path,
    storage_path_for,
    write_sidecar,
)
from ..crud import (
    create_queued_run,
    create_recording,
    delete_recording,
    get_recording,
    get_recording_by_uid,
    get_stats,
    list_recordings,
)
from .. import crud
from ..db import engine, get_session
from ..models import (
    Recording,
    RecordingShare,
    TranscriptionResult,
    TranscriptionRun,
    User,
)
from ..permissions import ensure_access, get_access_level
from ..queue import QueueError, QueueFullError, queue_manager
from ..export import (
    TemplateInvalid,
    TemplateNotFound,
    export_templates_dir,
    list_templates,
    load_template,
    render_template,
)
from ..export_backup import build_backup_zip
from ..versions import list_versions
from ..service import _current_run, resegment_by_duration, trim_audio
from ..whatsapp import parse_whatsapp
from ..timeutil import iso_utc
from ..eta import elapsed_since, estimate_align_eta_s, estimate_diar_eta_s, estimate_eta_s

router = APIRouter(prefix="/api")

log = __import__("logging").getLogger(__name__)

_LEARNER_TTL_S = 5.0
#: Change 085: TTL-Cache für den ETA-Learner (ändert sich nur bei
#: Job-Abschluss/Admin-Reset — kein DB-Read je Listen-Poll nötig).
_learner_cache: Dict[str, Any] = {"ts": 0.0, "learner": None}


def _eta_learner():
    """Gelernter ETA-Learner (max. 5 s alt); None bei Fehler (Fallback-Pfad)."""
    import time as _time
    from ..learner_store import load_learner

    now = _time.monotonic()
    if now - _learner_cache["ts"] > _LEARNER_TTL_S:
        try:
            _learner_cache["learner"] = load_learner()
        except Exception:
            _learner_cache["learner"] = None
        _learner_cache["ts"] = now
    return _learner_cache["learner"]

_HEALTH_WAIT_S = 120
_HEALTH_POLL_S = 2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user(request: Request, session=None) -> int | None:
    """Current user_id — OIDC-Session oder Cookie-gebundene anon-Session (B3)."""
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _key_cap(request, session=None) -> Optional[str]:
    """Rechte-Deckel aus einem API-Key (Task C3); None ohne Bearer."""
    from ..identity import current_identity

    return current_identity(request, session).key_level


def _is_admin_session(request: Request) -> bool:
    """Admin-Check wie in queue_api/deps — OIDC-Session-Flag."""
    from ..config import settings

    if not settings.OIDC_ENABLED:
        return False
    return bool(request.session.get("is_admin"))


def _is_anon_user(session, uid: Optional[int]) -> bool:
    """Change 014: User-Ordner-Wahl — anon-Sessions (kind='anonymous')
    oder kein User → AUDIO_DIR/anon/, eingeloggte User → /<user_id>/."""
    if uid is None:
        return True
    user = session.get(User, uid)
    return user is None or user.kind == "anonymous"


def _audio_file_exists(rec: Recording) -> bool:
    """True, wenn zur Aufnahme eine Audiodatei auf der Platte liegt.

    Self-Healing (Change 023): stored_path ist ein absoluter Pfad
    (AUDIO_DIR/<user>/<uuid><ext>) — Existenz direkt prüfbar.
    """
    return bool(rec.stored_path) and Path(rec.stored_path).is_file()


def _ensure_audio_present(rec: Recording) -> None:
    """410 statt 500, wenn die Audiodatei fehlt (Self-Healing).

    Aufnahmen ohne Datei (Crash zwischen File-Write und DB-Commit,
    manueller DB-Eingriff, Platten-Verlust) dürfen keinen 500-Crash
    auslösen — die GUI markiert sie als defekt (audio_missing).
    """
    if not _audio_file_exists(rec):
        raise HTTPException(status_code=410, detail="audio file missing")


def ensure_backend_available(backend: str, request: Request) -> None:
    """Ensure a non-default backend can accept jobs.

    - Default (ps-pk-onnx) always runs as part of the core stack → no-op.
    - Admin: tries to start the container when it is not running
      (resource check + health wait), 409 when the start fails.
    - Anonymous: 409 when the backend is not already running — anon users
      only get offered running backends by the frontend anyway.
    """
    from ..config import settings
    from ..docker_proxy import DockerProxyClient, DockerProxyError, get_docker_client
    from ..service_registry import container_name as _cn, get_service

    if not backend or backend == settings.POLYSCHNACK_DEFAULT_BACKEND:
        return

    svc = get_service(backend)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"unknown backend {backend}")

    profile = svc["compose_profile"]
    container = _cn(svc)  # Option C: Container-Name = Service-Name

    docker: DockerProxyClient = get_docker_client()
    try:
        state = docker.container_state(container)
    except DockerProxyError as exc:
        log.warning("transcribe: docker-proxy unreachable for %s: %s", container, exc)
        raise HTTPException(status_code=503, detail=f"docker-proxy unreachable: {exc}")

    if state and state.get("running"):
        return

    # Not running → only admins may auto-start it.
    if not _is_admin_session(request):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Backend {backend} ist nicht gestartet. Bitte wähle ein "
                "laufendes Backend (Admin: startet es automatisch)."
            ),
        )

    # Admin path: resource check → start → health wait.
    from ..resources import check_resources

    try:
        rep = check_resources(svc, docker)
        if not rep.ok:
            raise HTTPException(
                status_code=409,
                detail={"reason": "insufficient_resources", "message": rep.message},
            )
        docker.start(container)
    except DockerProxyError as exc:
        from ..docker_proxy import classify_docker_error

        gpu_msg = classify_docker_error(exc)
        if gpu_msg is not None:
            # Keine NVIDIA-GPU auf dem Host → verständliche Meldung statt
            # kryptischem Docker-Error (Hybrid: CPU-Backend wählen lassen).
            raise HTTPException(
                status_code=409,
                detail={"reason": "no_gpu", "message": gpu_msg},
            )
        raise HTTPException(status_code=503, detail=f"docker-proxy unreachable: {exc}")

    log.info("transcribe: admin auto-start %s (%s)", backend, container)
    deadline = time.monotonic() + _HEALTH_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(_HEALTH_POLL_S)
        try:
            st = docker.container_state(container)
        except DockerProxyError:
            st = None
        if st is None:
            continue
        if st.get("health") == "healthy" or (
            st.get("health") is None and st.get("status") == "running"
        ):
            return
    raise HTTPException(
        status_code=502,
        detail=f"Backend {backend} wurde gestartet, wurde aber nicht healthy ({_HEALTH_WAIT_S} s). "
               "Siehe Logs im Admin-Bereich.",
    )


_VRAM_CACHE: dict = {"ts": 0.0, "free_gb": None}


def _probe_host_vram_gb(ttl_s: float = 60.0):
    """Freier VRAM des Hosts (GB) via approach-a-/health.

    Proxy für ALLE Backends auf derselben GPU: nur unsere eigenen Server
    (approach-a/ps-pk-onnx) melden VRAM, die Crisp-Container sind fremde
    Images — deren Grenze leitet sich daher aus demselben Wert ab.
    Gecached (ttl_s), non-fatal: None bei Fehler (CPU-only, Backend down)
    → Aufrufer nutzt den statischen Fallback.
    """
    import time as _t

    from ..config import settings

    now = _t.monotonic()
    if now - _VRAM_CACHE["ts"] < ttl_s:
        return _VRAM_CACHE["free_gb"]
    free = None
    try:
        import httpx

        r = httpx.get(f"{settings.ASR_URL}/health", timeout=2.0)
        r.raise_for_status()
        free = r.json().get("resources", {}).get("vram_free_gb")
    except Exception:
        free = None
    _VRAM_CACHE["ts"] = now
    _VRAM_CACHE["free_gb"] = free
    return free


def _check_long_audio(backend: str, rec) -> None:
    """VRAM-Prognose VOR dem Transkribieren (User-Befund 2026-08-14).

    Eine zu lange Datei für das gewählte Backend führte bisher erst NACH dem
    CUDA-OOM zu einer Fehlermeldung. Diese Prüfung schlägt VOR dem Enqueue
    fehl (409) und sagt dem User, was zu tun ist: Live-Modus aktivieren
    (Default-Backend, verarbeitet fensterweise) oder anderes Backend wählen.

    Die Grenze kommt aus backends.yaml (`long_audio.max_safe_duration_s`).
    Da Alt-Aufnahmen eine grobe Größen-Schätzung als Dauer haben, wird bei
    Überschreitung die ECHTE Dauer per ffprobe nachgemessen, bevor geurteilt
    wird — kein Fehlalarm durch den alten Schätzwert.
    """
    from ..service_registry import get_service

    svc = get_service(backend)
    if not svc:
        return
    la = svc.get("long_audio") or {}
    max_safe = la.get("max_safe_duration_s")
    # Dynamische Grenze (auto_vram): der freie Host-VRAM bestimmt die sichere
    # Dauer — Crisp-Backends laden die Datei am Stück, dort skaliert der VRAM
    # mit der Länge. Gemessen wird im approach-a-/health (gleiche GPU für alle
    # Backends); ohne Messwert → statischer Fallback (max_safe als Hard-Cap).
    if la.get("auto_vram"):
        free = _probe_host_vram_gb()
        per_min = float(la.get("vram_per_minute_gb") or 0.04)
        safety = float(la.get("vram_safety_gb") or 2.0)
        if free is not None and per_min > 0:
            dynamic_s = max(0.0, free - safety) / per_min * 60.0
            max_safe = min(dynamic_s, max_safe) if max_safe else dynamic_s
    if not max_safe or max_safe <= 0:
        return

    duration = rec.duration_s or 0.0
    if duration > max_safe:
        # Alt-Datensätze: echte Dauer nachmessen statt dem Schätzwert glauben.
        # Datei-basiert (ffprobe) — read_bytes() lud die komplette Datei in
        # den RAM (bei 357-MB-Files die OOM-Falle wie beim alten Peaks-Pfad).
        stored = Path(rec.stored_path)
        if stored.exists():
            probed = probe_duration_path(stored) or 0.0
            if probed > 0:
                duration = probed
    if duration <= max_safe:
        return

    minutes = int(duration // 60)
    limit_min = int(max_safe // 60)
    can_stream = bool(la.get("streaming_advice", False))
    if can_stream:
        hint = (
            f"Bitte den Live-Modus aktivieren (verarbeitet die Datei in "
            f"kleinen Fenstern statt am Stück) und erneut versuchen."
        )
    else:
        hint = (
            f"Dieses Backend unterstützt keinen Live-Modus — bitte das "
            f"Default-Backend (ps-pk-onnx) mit aktiviertem Live-Modus wählen "
            f"oder eine kürzere Datei nutzen."
        )
    raise HTTPException(
        status_code=409,
        detail=(
            f"Datei ist {minutes} min lang — für Backend '{backend}' ist die "
            f"sichere Grenze {limit_min} min (Bearbeitungslimit). {hint}"
        ),
    )


_peaks_inflight: set[int] = set()

#: Wie viele peaks-lose Aufnahmen der GET /recordings-Abruf sofort nachzieht
#: (nur die sichtbaren); der Rest kommt vom periodischen Backfill-Loop.
_PEEKS_LIST_NAACHZUG = 5


def _backfill_peaks_batch(limit: int = 2) -> int:
    """Serieller Peaks-/Preview-Backfill: berechnet bis zu *limit* fehlende
    Assets (Peaks UND Playback-Preview).

    Läuft periodisch im Hintergrund-Loop (main.py) statt bei jedem
    GET /recordings für alle Dateien Threads zu feuern (2026-08-15:
    Dutzende parallele ffmpeg-Voll-Decodes bei vielen Alt-Aufnahmen →
    CPU/RAM-Kollaps, Seite ewig langsam). Bewusst langsam: 1-2 Dateien
    pro Durchlauf, dann Pause — der Viewport-Nachzug (Frontend) und der
    Upload-Pfad bleiben unberührt.

    Seit 2026-08-15 zusätzlich: fehlende Playback-Previews (64-kbps-MP3-
    Sidecar) werden im selben seriellen Durchlauf erzeugt — der Player
    lädt damit statt der vollen WAV nur die kleine Datei.
    """
    from ..crud import list_recordings_missing_peaks
    from ..db import engine as _engine
    from sqlmodel import Session as _Session
    from ..peaks import compute_preview_path
    from ..service import _compute_peaks_path

    done = 0
    try:
        with _Session(_engine) as s:
            for rec in list_recordings_missing_peaks(s, limit=limit):
                rid = int(rec.id)
                if rid in _peaks_inflight:
                    continue
                _peaks_inflight.add(rid)
                try:
                    src = Path(rec.stored_path)
                    # 1) Preview-Sidecar (schlank fürs Browser-Playback)
                    prev_path = getattr(rec, "preview_path", None)
                    if not (prev_path and Path(prev_path).exists()):
                        prev = compute_preview_path(src)
                        if prev and Path(prev).exists():
                            rec.preview_path = str(prev)
                            rec.preview_size_bytes = Path(prev).stat().st_size
                    # 2) Waveform-Peaks
                    if not getattr(rec, "waveform_peaks", None):
                        peaks = _compute_peaks_path(src)
                        if peaks:
                            rec.waveform_peaks = peaks
                    if getattr(rec, "preview_path", None) or getattr(rec, "waveform_peaks", None):
                        s.add(rec)
                        s.commit()
                        done += 1
                    # beide leer (Decode-Fehler) → beim nächsten Durchlauf
                    # erneut versuchen (kein Inflight-Block, kein Commit)
                finally:
                    _peaks_inflight.discard(rid)
    except Exception:
        log.exception("peaks: backfill batch failed")
    return done


def _schedule_peaks(rec_id: int) -> None:
    """Waveform-Peaks (Mini-Preview für WaveSurfer) direkt nach Upload/Import,
    Transcribe oder Listen-Abruf im Hintergrund berechnen — die Wellenform ist
    damit SOFORT da, unabhängig von der Transkription (vorher erst nach
    erfolgreichem Transcribe; bei langen Dateien, deren Transkription
    fehlschlug, blieb die Waveform kaputt). Fehler sind bewusst nicht-fatal
    (nur Log) — das Rendern fällt dann auf WaveSurfers eigenes Decoding zurück.

    Läuft in einem eigenen Thread: die Routen sind sync (Starlette-Threadpool)
    und haben dort KEINEN Event-Loop — asyncio.get_running_loop() wirft dort
    immer RuntimeError, die Peaks kämen sonst nie an (Regression 2026-08-14).
    """
    if rec_id in _peaks_inflight:
        return
    # Change 155 (Schritt 6): statt nacktem Thread als Queue-Job (eigener
    # "peaks"-Slot, Kapazität 1). Dedup doppelt: Queue-Key (Job in _jobs)
    # + _peaks_inflight-Guard (Berechnung läuft bereits, s. run_peaks_job).
    from ..queue import QueueError, queue_manager

    try:
        queue_manager.enqueue(
            rec_id, user_id=None, backend="peaks", kind="peaks",
            key=f"peaks-{rec_id}",
        )
    except QueueError:
        log.warning("peaks: Job für rec_id=%s bereits in der Queue", rec_id)


def run_peaks_job(rec_id: int) -> None:
    """Change 155 (Schritt 6): Queue-Dispatch-Ziel für peaks-Jobs.

    Der Inflight-Guard lebt HIER (um die tatsächliche Berechnung), nicht im
    Trigger: nur der wirklich laufende Job blockiert Doppel-Starts — ein
    fehlgeschlagener/gemockter enqueue hinterlässt kein verwaistes Set."""
    if rec_id in _peaks_inflight:
        return
    _peaks_inflight.add(rec_id)
    try:
        _compute_peaks_background(rec_id)
    finally:
        _peaks_inflight.discard(rec_id)


def _compute_peaks_background(rec_id: int) -> None:
    try:
        from sqlmodel import Session as _Session

        from ..crud import get_recording as _gr
        from ..db import engine as _engine
        from ..peaks import compute_preview_path
        from ..service import _compute_peaks_path

        with _Session(_engine) as s:
            rec = _gr(s, rec_id)
            if rec is None:
                return
            src = Path(rec.stored_path)
            # 1) Playback-Preview-Sidecar (64-kbps-MP3) — fehlt sie, wird sie
            #    hier erzeugt; der Player lädt damit statt der vollen WAV nur
            #    die kleine Datei (2026-08-15).
            prev_path = getattr(rec, "preview_path", None)
            if not (prev_path and Path(prev_path).exists()):
                prev = compute_preview_path(src)
                if prev and Path(prev).exists():
                    rec.preview_path = str(prev)
                    rec.preview_size_bytes = Path(prev).stat().st_size
            # 2) Waveform-Peaks
            if not getattr(rec, "waveform_peaks", None):
                # Pfad-basiert (statt read_bytes): 357-MB-Files würden sonst
                # das RAM-Limit sprengen (OOM-Kill, s. peaks.compute_peaks_path).
                peaks = _compute_peaks_path(src)
                if peaks:
                    rec.waveform_peaks = peaks
            if getattr(rec, "preview_path", None) or getattr(rec, "waveform_peaks", None):
                s.add(rec)
                s.commit()
    except Exception:
        log.exception("peaks: background compute failed for rec_id=%s", rec_id)
    finally:
        _peaks_inflight.discard(rec_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUDIO_MIME_FALLBACK = "audio/mpeg"

# Browser-nativ abspielbare Formate (inkl. Safari/iOS) — Referenz auf die
# Storage-Policy in audio_utils.NATIVE_AUDIO_EXTS. Alles andere wird beim
# Upload nach MP3 konvertiert (.aac/.ogg/.opus/.webm/.wma/…).
_BROWSER_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".m4b", ".mp4", ".flac"}

# Change 008: Media-Types für Export-Templates (nach Datei-Endung).
_EXPORT_MEDIA_TYPES = {
    "txt": "text/plain",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "csv": "text/csv",
    "ass": "text/plain",
    "json": "application/json",
    "jsonl": "application/jsonl",
    "html": "text/html",
}

# Change 015: Maschinenlesbare Formate bleiben reines UTF-8 (kein BOM);
# alle anderen (Text-Formate für Editoren/Excel) bekommen UTF-8-BOM.
_JSON_EXPORT_EXTS = {"json", "jsonl"}


def _encode_export(content: str, ext: str) -> bytes:
    """Encodiert Export-Inhalt: utf-8-sig (BOM) für Text, utf-8 für JSON.

    Fix 2026-08-18 (Change 015, User-Report Regression): Der bisherige
    charset=utf-8-Header reicht nicht — Windows-Editoren (Notepad < 1903,
    Excel, ältere Tools) raten UTF-8 ohne BOM als Latin-1 → „Ã¤". Mit
    BOM erkennen sie die Umlaute zuverlässig.
    """
    if ext.lower() in _JSON_EXPORT_EXTS:
        return content.encode("utf-8")
    return content.encode("utf-8-sig")


def _queue_position_for(rec_id: Optional[int]) -> Optional[int]:
    """Queue-Position der Aufnahme (0 = nicht in der Warteschlange)."""
    if not rec_id:
        return None
    try:
        pos = queue_manager.position(rec_id)
        return pos if pos > 0 else None
    except Exception:
        return None


def _queue_eta_s_for(rec_id: Optional[int]) -> Optional[int]:
    """Geschätzte Wartezeit in Sekunden (Position × Ø-Verarbeitungszeit)."""
    if not rec_id:
        return None
    try:
        pos = queue_manager.position(rec_id)
        if pos <= 0:
            return None
        with Session(engine) as session:
            avg_ms = crud.avg_recent_processing_ms(session)
        if not avg_ms:
            return None
        return round(pos * avg_ms / 1000)
    except Exception:
        return None


def _recording_to_dict(
    rec: Recording,
    access_level: Optional[str] = None,
    lite: bool = False,
    run: Optional[Any] = None,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    """Serialise a Recording row to the canonical API response shape.

    Change 059: `lite=True` (Listen-Payload) lässt die datenintensiven Felder
    weg (`text`, `segments`, `waveform_peaks` = None) — die Karten-Shell
    lädt auch im langsamen Netz sofort; Transkription + Peaks holt das
    Frontend pro Karte über GET /api/recordings/{rid} nach.

    Change 099: Settings (enable_* usw.) kommen aus dem TranscriptionRun
    (versionierte Wahrheit) — Aufrufer mit bekanntem Run reichen ihn als
    `run` durch; sonst wird er hier geladen.
    """
    uid = rec.uid or str(rec.id)  # fallback for legacy rows without uid
    if run is None and session is not None:
        run = _current_run(session, rec)
    _s_vad = bool(run and run.enable_vad)
    _s_diarize = bool(run and run.enable_diarize)
    _s_diarize_num = run.diarize_num_speakers if run else None
    _s_diarize_off = run.diarize_min_duration_off if run else None
    _s_diarize_method = run.diarize_method if run else None
    _s_streaming = bool(run and run.enable_streaming)
    _s_noise = True if run is None else bool(run.enable_noise_reduce)
    _s_enhance = "off" if run is None else (run.enable_enhance or "off")
    _s_punct = bool(run and run.enable_punctuation)
    # Change 082: ETA-Rest aus Audio-Dauer × RTF (nur während processing).
    # Change 127: auch bei done + laufender Rediarize (nur Diar-Phase,
    # Basis phase_started_at = Beginn der Rediarize-Note).
    if rec.status == "processing":
        eta = estimate_eta_s(
            rec.duration_s,
            rec.backend,
            enable_vad=_s_vad,
            enable_diarize=_s_diarize,
            diarize_method=_s_diarize_method,
            enable_noise_reduce=_s_noise,
            enable_enhance=_s_enhance,
            enable_punctuation=_s_punct,
            elapsed_s=elapsed_since(rec.processing_started_at),
            # Change 085: selbstlernende Faktoren (gelernt > Fallback > None).
            learner=_eta_learner(),
        )
    elif rec.status == "done" and rec.diar_status in ("running", "pending"):
        eta = estimate_diar_eta_s(
            rec.duration_s,
            diarize_method=_s_diarize_method,
            elapsed_s=elapsed_since(rec.phase_started_at),
            learner=_eta_learner(),
        )
    elif rec.status == "done" and rec.alignment in ("running", "pending"):
        # Change 127: Align-ETA analog (Background-Alignment).
        eta = estimate_align_eta_s(
            rec.duration_s,
            elapsed_s=elapsed_since(rec.phase_started_at),
            learner=_eta_learner(),
        )
    else:
        eta = None
    return {
        "id": rec.id,
        "uid": uid,
        "original_name": rec.original_name,
        # Change 014: editierbarer Titel; Fallback original_name.
        "title": rec.title or rec.original_name,
        # Change 054: freie Tags (Gruppierung/Filtrierung der Liste).
        "tags": list(rec.tags or []),
        "owner_user_id": rec.owner_user_id,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "duration_s": rec.duration_s,
        "status": rec.status,
        "text": None if lite else rec.text,
        "error": rec.error,
        # Self-Healing (Change 023): Datei weg → sichtbares Flag statt
        # stiller Fehler; UI kann Defekt-Badge zeigen, Export schreibt
        # AUDIO_FEHLT.txt statt zu crashen.
        "audio_missing": bool(rec.stored_path)
        and not Path(rec.stored_path).is_file(),
        "processing_ms": rec.processing_ms,
        # Change 086: Job-Kosten in Cent (User sichtbar; null = nicht bepreist).
        "cost_cents": rec.cost_cents,
        "reserved_cents": rec.reserved_cents,
        # Change 045: Status des präzisen Alignments (done|pending|running|skipped).
        "alignment": getattr(rec, "alignment", "done"),
        # Change 057: Status der Diarization (done|pending|running|failed|skipped).
        "diar_status": getattr(rec, "diar_status", "done"),
        "progress_pct": rec.progress_pct,
        "progress_note": rec.progress_note,
        # Change 011: Aktivitäts-/Phasen-Zeitstempel (Heartbeat).
        "phase_started_at": (
            iso_utc(rec.phase_started_at) if rec.phase_started_at else None
        ),
        "last_heartbeat_at": (
            iso_utc(rec.last_heartbeat_at) if rec.last_heartbeat_at else None
        ),
        # Change 082: Job-Beginn + gewähltes Backend (ETA-RTF-Quelle).
        "processing_started_at": (
            iso_utc(rec.processing_started_at) if rec.processing_started_at else None
        ),
        "backend": rec.backend,
        # Change 011: Queue-Position + Warte-ETA auf der Recording-Karte
        # (Werte wie im Queue-Watcher, aber direkt an der Aufnahme).
        "queue_position": _queue_position_for(rec.id) if rec.status == "queued" else None,
        "queue_eta_s": _queue_eta_s_for(rec.id) if rec.status == "queued" else None,
        "queue_backend": rec.backend if rec.status == "queued" else None,
        "created_at": iso_utc(rec.created_at),
        "language": rec.language,
        "segments": None if lite else rec.segments,
        # Change 009: manuelle Segment-Aufteilung aktiv (Anzeige nutzt
        # segments direkt, keine Auto-Re-Segmentierung nach segMaxDuration).
        "segments_manual": bool(getattr(rec, "segments_manual", False)),
        "audio_url": f"/api/recordings/{uid}/audio",
        # Schlanke Playback-Preview (64-kbps-MP3-Sidecar) — der Player lädt
        # NUR diese kleine Datei; die volle Datei bleibt für Download und
        # Transkription. Fehlt die Preview (noch nicht generiert), fällt
        # das Frontend auf audio_url zurück.
        "audio_preview_url": (
            f"/api/recordings/{uid}/audio/preview"
            if getattr(rec, "preview_path", None)
            else None
        ),
        "download_url": f"/api/recordings/{uid}/download",
        # Change 015: vollständiger Backup-Download (ZIP: Audio + Transkript
        # + Word-Timings + Versionen + manifest) — nur bei status=done
        # sinnvoll, URL ist aber immer verfügbar (Backend antwortet 409).
        "backup_url": f"/api/recordings/{uid}/backup",
        # WhatsApp / batch fields
        "batch_id": rec.batch_id,
        "recorded_at": iso_utc(rec.recorded_at) if rec.recorded_at else None,
        "source": rec.source,
        "enable_vad": _s_vad,
        "enable_diarize": _s_diarize,
        "diarize_num_speakers": _s_diarize_num,
        "diarize_min_duration_off": _s_diarize_off,
        "diarize_method": _s_diarize_method,
        "enable_streaming": _s_streaming,
        "enable_noise_reduce": _s_noise,
        "enable_enhance": _s_enhance,
        "waveform_peaks": None if lite else rec.waveform_peaks,
        "updated_at": iso_utc(rec.updated_at) if getattr(rec, "updated_at", None) else None,
        "user_id": rec.user_id,
        "access_level": access_level,
        "is_anon_shared": bool(getattr(rec, "share_token", False)),
        "retention_minutes": settings.POLYSCHNACK_ANON_RETENTION_MINUTES,
        "shared_at": iso_utc(rec.shared_at) if getattr(rec, "shared_at", None) else None,
        "delivery_status": rec.delivery_status,
        "delivery_error": rec.delivery_error,
        # Change 082: ETA aus Audio-Dauer × RTF — nur processing, nur mit
        # bekannter Rate (Anti-Fake: None statt geratenem Wert).
        "eta_total_s": eta[0] if eta else None,
        "eta_low_s": eta[1] if eta else None,
        "eta_high_s": eta[2] if eta else None,
    }


def _guess_mime(stored_path: str, stored_mime: str) -> str:
    """Return a usable audio MIME type for *stored_path*.

    Falls back to *_AUDIO_MIME_FALLBACK* when guessing fails.
    """
    if stored_mime and stored_mime != "application/octet-stream":
        return stored_mime
    guessed, _ = mimetypes.guess_type(stored_path)
    return guessed or _AUDIO_MIME_FALLBACK


def _convert_to_wav_if_needed(raw: bytes, original_name: str) -> tuple[bytes, str, str | None]:
    """Immer-Konvertierung nach 16-kHz-mono-WAV via ffmpeg (pipe).

    Returns (audio_bytes, final_extension, conversion_note).

    Seit 2026-08-14 wird das NUR noch für exotische Upload-Formate und für
    Backends ohne Compressed-Support (on-the-fly beim Transkribieren)
    genutzt — native Formate (MP3/OGG/…) gehen unkonvertiert in den Store.
    Fehler → HTTPException 400.
    """
    try:
        return convert_to_wav_16k_mono(raw, original_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def _effective_vad_mode(run) -> str:
    """Change 114: effektiver VAD-Modus aus dem Run (Legacy-Fallback).

    Alte Runs haben nur enable_vad (bool) → True wird zu "edges". Neue Runs
    tragen vad_mode ("off"|"edges"|"all"). None/"" (fehlende Spalte in alten
    DBs) fällt auf den bool zurück.
    """
    if run is None:
        return "off"
    mode = getattr(run, "vad_mode", None) or ""
    if mode in ("off", "edges", "all"):
        return mode
    return "edges" if run.enable_vad else "off"


@router.post("/recordings", status_code=201)
async def upload_recording(
    request: Request,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
    enable_vad: bool = Form(False),
    vad_mode: str = Form("off"),  # Change 114: off|edges|all
    enable_diarize: bool = Form(False),
    diarize_num_speakers: Optional[int] = Form(None),
    diarize_min_duration_off: Optional[float] = Form(None),
    diarize_method: Optional[str] = Form(None),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
    separate_backend: str = Form("none"),  # Change 106: none|htdemucs|mel-band-roformer
    session: Session = Depends(get_session),
) -> Any:
    """Accept a multipart audio upload, persist it."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")
    # Direkte Funktionsaufrufe (Tests) liefern Form(...)-Objekte statt Strings.
    if not isinstance(separate_backend, str):
        separate_backend = "none"
    if not isinstance(vad_mode, str) or vad_mode not in ("off", "edges", "all"):
        vad_mode = "edges" if enable_vad else "off"  # Change 114: Legacy-Ableitung
    elif enable_vad and vad_mode == "off":
        vad_mode = "edges"  # Change 114: alter Client sendet nur enable_vad=true
    enable_vad = vad_mode != "off"  # Change 114: konsistente Ableitung (Legacy-Leser)

    # Limit upload size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"file too large (max {settings.MAX_UPLOAD_SIZE_MB} MB)")
    await file.close()

    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    # Compute content hash for duplicate detection
    content_hash = hashlib.blake2b(raw, digest_size=16).hexdigest()
    current_user_id = _current_user(request, session)
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()

    # Duplikat nur melden, wenn der Treffer DEM OWNER gehört (Review
    # 2026-08-15, P1): die Query war nicht auf den Owner gescoped — wer eine
    # Datei hochlädt, die ein anderer schon hochgeladen hat, bekam DESSEN
    # Transkript (text/segments/uid) zurück. url_import.py macht es bereits
    # korrekt — gleiches Owner-Prädikat hier.
    if (
        existing
        and existing.user_id == current_user_id
        and not (request.query_params.get("force") == "true")
        and Path(existing.stored_path).is_file()
    ):
        # Share-Target (Android): direkt zur bestehenden Aufnahme springen
        # statt JSON — der Browser öffnet die PWA auf /r/{uid}.
        if request.query_params.get("from") == "share" and existing.uid:
            return RedirectResponse(f"/r/{existing.uid}", status_code=303)
        return {
            "duplicate": True,
            "existing_id": existing.id,
            "recording": _recording_to_dict(existing, session=session),
        }

    # Storage-Policy (2026-08-14): native Formate (MP3/OGG/WebM/…) werden
    # UNKONVERTIERT gespeichert — WaveSurfer (Browser) und die ASR-Backends
    # (ffmpeg-Decode) können sie nativ. Nur exotische Formate → 16-kHz-mono-WAV.
    # Befund 2026-08-21: sehr kurze/kaputte Recorder-Blobs warfen hier einen
    # RuntimeError → 500. Jetzt sauberes 422, damit der Pending-Upload-Flow
    # („recording saved locally, upload pending") verständlich fehlschlägt
    # und der Eintrag nicht endlos hängt.
    try:
        audio_data, new_ext, conv_note = prepare_storage(raw, file.filename)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Audio konnte nicht gelesen werden (Datei zu kurz oder beschädigt): {exc}",
        ) from None

    # Review 2026-08-15 (P1): Quota-Check VOR dem Write — der bisherige
    # Ablauf schrieb die Datei zuerst und prüfte dann, so blieben bei
    # über-Quota-Uploads Orphan-Dateien auf der Platte liegen. Größe +
    # Disk-Summe werden vor dem Schreiben geprüft (die exakte Dauer kommt
    # nach dem Write per ffprobe; schlägt der Dauer-Check fehl, wird die
    # frisch geschriebene Datei sofort wieder entfernt).
    uid = _current_user(request, session)
    from ..anon_limits import enforce_anon_limits

    anon_user = session.get(User, uid) if uid is not None else None
    enforce_anon_limits(session, anon_user, len(audio_data), duration_s=None)

    stored = storage_path_for(
        uid, new_ext,
        anon=anon_user is None or anon_user.kind == "anonymous",
    )
    stored.write_bytes(audio_data)

    # Change 018: Bei echter Transkodierung (Endung geändert, z. B. .aac →
    # MP3) das unveränderte Original aufbewahren — Export/Backup liefert es
    # als audio.original.<ext>. Native Uploads & Faststart-Remux (Endung
    # gleich) bekommen kein Duplikat.
    orig_path = None
    orig_ext = Path(file.filename).suffix.lower() or ".bin"
    if conv_note and orig_ext != new_ext:
        orig_path = original_path(stored, orig_ext)
        orig_path.write_bytes(raw)

    recorded_at, source = parse_whatsapp(file.filename)

    # Exakte Dauer via ffprobe — Grundlage für die VRAM-Prognose und die ETA.
    # Datei-basiert (Pipe liefert bei nicht-seekbarem Input oft „N/A"; der
    # alte Größen-Fallback war bei 128-kbps-MP3 um Faktor 2 daneben und
    # hätte Long-Audio-Grenzen/Quota falsch ausgelöst).
    est_duration_s = probe_duration_path(stored) or (len(raw) / 8000)

    # Dauer-Limit NACH dem ffprobe — bei Fehlschlag Datei aufräumen.
    try:
        enforce_anon_limits(session, anon_user, len(audio_data), est_duration_s)
    except HTTPException:
        try:
            stored.unlink(missing_ok=True)
        except OSError:
            pass
        if orig_path:
            try:
                orig_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    # Append conversion note to original name so the user knows
    display_name = file.filename
    if conv_note:
        display_name = f"{file.filename} {conv_note}"

    rec = create_recording(
        session,
        original_name=display_name,
        stored_path=str(stored),
        mime="audio/wav" if new_ext == ".wav" else (file.content_type or "application/octet-stream"),
        size_bytes=len(audio_data),
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        duration_s=est_duration_s,
        content_hash=content_hash,
        user_id=uid,
        owner_user_id=uid,
    )
    # Change 099: Settings landen im queued-Run (Recording = Stamm ohne
    # Settings-Spalten); process_recording übernimmt den ältesten queued-Run.
    run = create_queued_run(
        session, rec.id,
        enable_vad=enable_vad,
        vad_mode=vad_mode,  # Change 114
        enable_diarize=enable_diarize,
        diarize_num_speakers=diarize_num_speakers,
        diarize_min_duration_off=diarize_min_duration_off,
        diarize_method=diarize_method,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        separate_backend=separate_backend,  # Change 106 (Fix 23.08.: Feld wurde ignoriert)
        user_id=uid,
    )
    rec.current_run_id = run.id
    session.add(rec)
    session.commit()
    if rec.id is not None:
        _schedule_peaks(rec.id)  # Waveform-Preview sofort im Hintergrund rechnen
    # Share-Target (Android): nach dem Upload zur Aufnahme springen — der
    # Browser folgt dem 303 und öffnet die PWA auf /r/{uid}. Ohne den
    # Query-Parameter bleibt es beim JSON für die SPA (Upload-Formular).
    if request.query_params.get("from") == "share" and rec.uid:
        return RedirectResponse(f"/r/{rec.uid}", status_code=303)
    return _recording_to_dict(rec, session=session)


@router.post("/recordings/{rid}/duplicate", status_code=201)
def duplicate_recording(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Neue Aufnahme aus einer vorhandenen Datei anlegen (Duplikat-Upload).

    Der Upload-Endpoint hat die Datei bereits als Duplikat erkannt (gleicher
    content_hash) — statt sie beim „Upload again" ein zweites Mal übers Netz
    zu übertragen (bei 300+-MB-Dateien blieb der Dialog minutenlang bei 100%
    ohne Feedback), legt dieser Endpoint sofort eine neue Recording-Row an:
    Datei-Kopie auf Platte, identische Waveform-Peaks (gleicher Inhalt →
    gleiche Wellenform — spart den ffmpeg-Decode), gleiche Feature-Flags.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

    _ensure_audio_present(rec)   # 410 statt 409/500 (Self-Healing)
    src = Path(rec.stored_path)
    new_path = storage_path_for(
        uid, src.suffix.lower() or ".bin",
        anon=_is_anon_user(session, uid),
    )
    import shutil

    shutil.copy2(src, new_path)

    from ..service import _current_run
    src_run = _current_run(session, rec)  # Change 099: Settings aus dem Run
    new_rec = create_recording(
        session,
        original_name=rec.original_name,
        stored_path=str(new_path),
        mime=rec.mime or "application/octet-stream",
        size_bytes=rec.size_bytes or 0,
        batch_id=None,
        recorded_at=rec.recorded_at,
        source=rec.source,
        duration_s=rec.duration_s,
        content_hash=rec.content_hash,
        user_id=uid,
    )
    # Change 099: Settings des Originals (aktueller Run) in den queued-Run
    # des Duplikats kopieren — das Recording selbst trägt keine Settings.
    run = create_queued_run(
        session, new_rec.id,
        backend=src_run.backend if src_run else "ps-pk-onnx",
        enable_vad=bool(src_run and src_run.enable_vad),
        vad_mode=_effective_vad_mode(src_run),  # Change 114
        enable_diarize=bool(src_run and src_run.enable_diarize),
        diarize_num_speakers=src_run.diarize_num_speakers if src_run else None,
        diarize_min_duration_off=src_run.diarize_min_duration_off if src_run else None,
        diarize_method=src_run.diarize_method if src_run else None,
        enable_streaming=bool(src_run and src_run.enable_streaming),
        enable_noise_reduce=True if src_run is None else bool(src_run.enable_noise_reduce),
        enable_enhance="off" if src_run is None else (src_run.enable_enhance or "off"),
        separate_backend="none" if src_run is None else (src_run.separate_backend or "none"),  # Change 106
        prompt_template_id=src_run.prompt_template_id if src_run else None,
        delivery_target_id=src_run.delivery_target_id if src_run else None,
        llm_endpoint_id=src_run.llm_endpoint_id if src_run else None,
        user_id=uid,
    )
    new_rec.current_run_id = run.id
    session.add(new_rec)
    session.commit()
    if new_rec.id is not None:
        # Peaks übernehmen statt neu dekodieren — identischer Inhalt, und
        # bei 300+-MB-Dateien wäre der Voll-Decode der OOM-Trigger gewesen.
        new_rec.waveform_peaks = rec.waveform_peaks
        session.add(new_rec)
        session.commit()
    return _recording_to_dict(new_rec, session=session)


class MergeRequest(BaseModel):
    uids: List[str]
    batch_id: Optional[str] = None


@router.post("/recordings/merge", status_code=201)
def merge_recordings(
    req: MergeRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Mehrere Aufnahmen zu EINER Audiodatei zusammenführen (ffmpeg concat).

    Multi-Upload „Als eine Aufnahme zusammenführen": die Dateien werden in
    der angegebenen Reihenfolge zu 16-kHz-mono-WAV konkateniert (ffmpeg
    ``filter_complex concat`` — funktioniert mit gemischten Formaten, kein
    Codec-Gleichheits-Zwang wie beim concat-demuxer). Die Einzel-Aufnahmen
    werden danach gelöscht (Row + Datei) — übrig bleibt nur das gemergte
    Recording mit durchgehenden Timestamps.
    """
    if len(req.uids) < 2:
        raise HTTPException(
            status_code=400,
            detail="mindestens 2 Dateien zum Zusammenführen nötig",
        )
    uid = _current_user(request, session)
    cap = _key_cap(request, session)
    recs: List[Recording] = []
    for r_uid in req.uids:
        rec = get_recording_by_uid(session, r_uid)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"recording {r_uid} not found")
        ensure_access(session, rec, uid, "full", cap=cap)
        src = Path(rec.stored_path)
        if not src.is_file():
            raise HTTPException(status_code=409, detail=f"Datei von {rec.original_name} fehlt")
        recs.append(rec)

    inputs: List[str] = []
    for rec in recs:
        inputs += ["-i", rec.stored_path]
    n = len(recs)
    concat_filter = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    out_path = storage_path_for(uid, ".wav", anon=_is_anon_user(session, uid))
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        *inputs,
        "-filter_complex", concat_filter,
        "-map", "[out]",
        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        out_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409, detail="Zusammenführen abgebrochen (länger als 600s)"
        ) from None
    if proc.returncode != 0:
        out_path.unlink(missing_ok=True)
        err = proc.stderr.decode("utf-8", errors="replace")[:300]
        raise HTTPException(status_code=409, detail=f"ffmpeg concat fehlgeschlagen: {err}")

    # Größe + Hash streamend berechnen — kein 700-MB-RAM-Objekt (OOM-Lehre)
    size_bytes = out_path.stat().st_size
    h = hashlib.blake2b(digest_size=16)
    with open(out_path, "rb") as fh:
        while chunk := fh.read(1 << 16):
            h.update(chunk)

    duration_s = sum(rec.duration_s or 0.0 for rec in recs) or None
    names = " + ".join(rec.original_name for rec in recs[:2])
    if len(recs) > 2:
        names += f" +{len(recs) - 2}"

    new_rec = create_recording(
        session,
        original_name=f"Merge ({len(recs)} Dateien): {names}",
        stored_path=str(out_path),
        mime="audio/wav",
        size_bytes=size_bytes,
        batch_id=req.batch_id,
        duration_s=duration_s,
        content_hash=h.hexdigest(),
        user_id=uid,
    )
    if new_rec.id is not None:
        _schedule_peaks(new_rec.id)  # Waveform für das Merge-Ergebnis

    # Einzeldateien löschen (Row + Datei) — die Einzelnen waren nur das
    # Zwischenprodukt; übrig bleibt die eine gemergte Aufnahme.
    for rec in recs:
        path = Path(rec.stored_path)
        delete_recording(session, rec.id)
        path.unlink(missing_ok=True)
    return _recording_to_dict(new_rec, session=session)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


@router.get("/recordings")
def list_recordings_endpoint(
    q: Optional[str] = None,
    sort: str = "date",
    dir: str = "desc",
    tag: Optional[List[str]] = Query(None),
    # Change 059: Lite-Payload für die Liste (text/segments/peaks = None) —
    # das Frontend lädt die datenintensiven Felder pro Karte nach.
    lite: bool = Query(False),
    request: Request = None,
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Return recordings (Change 054: sortierbar + tag-filtrierbar).

    - *sort*: date (Default) | edited | name | filename | length
    - *dir*: desc (Default) | asc
    - *tag*: mehrfach; ODER-Filter auf die Tags der Aufnahmen
    """
    if dir not in ("asc", "desc"):
        dir = "desc"
    uid = _current_user(request, session)
    rows = list_recordings(
        session, q=q, user_id=uid, include_shares=uid is not None,
        sort=sort, dir=dir, tags=tag or None,
    )
    # Alt-Aufnahmen ohne Peaks (vor dem Peaks-Feature hochgeladen): nur die
    # ERSTEN (sichtbaren) sofort nachziehen — nicht alle. Früher wurde für
    # jede peaks-lose Aufnahme ein eigener ffmpeg-Thread gestartet; bei
    # vielen Dateien feuerten Dutzende Voll-Decodes gleichzeitig (Seite ewig
    # langsam, 2026-08-15). Den Rest füllt der periodische Backfill-Loop
    # seriell auf (main.py, alle User).
    for _rec in rows[:_PEEKS_LIST_NAACHZUG]:
        if not getattr(_rec, "waveform_peaks", None):
            _schedule_peaks(int(_rec.id))
    share_rec_ids = set()
    if uid is not None:
        share_rec_ids = {
            s.rec_id
            for s in session.exec(
                select(RecordingShare).where(RecordingShare.user_id == uid)
            ).all()
        }
    out = []
    # Change 067-Fix (Kollaboration): has_shares = der OWNER hat User-Shares
    # vergeben (rec_id in RecordingShare) — einmalige Query für die ganze
    # Liste. Das Frontend baut die Yjs-Verbindung nur dann auf („Kollaboration
    # möglich"), wenn has_shares || is_anon_shared || shared_with_me.
    shared_out_ids: set[int] = set()
    if uid is not None:
        shared_out_ids = {
            s.rec_id
            for s in session.exec(
                select(RecordingShare).where(RecordingShare.rec_id.in_([r.id for r in rows]))
            ).all()
        }
    for r in rows:
        d = _recording_to_dict(r, access_level=get_access_level(
            session, r, uid, cap=_key_cap(request, session)), lite=lite, session=session)
        d["shared_with_me"] = r.user_id != uid and r.id in share_rec_ids
        d["has_shares"] = r.id in shared_out_ids
        out.append(d)
    return out


@router.get("/recordings/{rid}")
def get_recording_endpoint(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Return a single recording dict including segments."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    d = _recording_to_dict(rec, access_level=get_access_level(
        session, rec, uid, cap=_key_cap(request, session)), session=session)
    # Visuelle Markierung: "shared_with_me" = fremde Recording via User-Share
    shared_with_me = False
    if uid is not None and rec.user_id != uid:
        shared_with_me = session.exec(
            select(RecordingShare).where(
                RecordingShare.rec_id == rec.id, RecordingShare.user_id == uid
            )
        ).first() is not None
    d["shared_with_me"] = shared_with_me
    # Change 067-Fix: has_shares (Owner hat User-Shares vergeben) → Frontend
    # baut die Yjs-Verbindung nur bei geteilten Aufnahmen auf.
    d["has_shares"] = session.exec(
        select(RecordingShare).where(RecordingShare.rec_id == rec.id)
    ).first() is not None
    # Debug: include word presence info without changing data
    segs = d.get("segments") or []
    d["_words_debug"] = {
        "total_segments": len(segs),
        "segs_with_words": sum(1 for s in segs if s.get("words") and len(s["words"]) > 0),
        "total_words": sum(len(s.get("words") or []) for s in segs),
    }
    return d


@router.get("/recordings/{rid}/peaks")
def get_progressive_peaks(
    rid: str,
    request: Request,
    length: int = Query(2000, ge=2000, le=300000),
    session: Session = Depends(get_session),
) -> Response:
    """Change 155 (Timing-Zoom): progressive Peaks mit wählbarer Auflösung.

    Die Detail-Karte liefert 2000 Punkte (Basis-Auflösung) — für den
    Wort-Zoom (~30 % sichtbar) fordert der Timing-Tab feinere Peaks an
    (?length=N, bis 300000). Die Peaks sind deterministisch (nur vom Audio
    abhängig) → Cache-Control für den Browser-Cache.
    """
    from pathlib import Path as _P

    from ..peaks import compute_peaks_path

    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    src = _P(rec.stored_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail="audio missing")
    try:
        peaks = compute_peaks_path(src, n_bins=length)
    except Exception:
        log.exception("peaks: progressive compute failed for rid=%s", rid)
        raise HTTPException(status_code=500, detail="peaks failed") from None
    if not peaks:
        raise HTTPException(status_code=422, detail="no audio decodable")
    return JSONResponse(
        {"peaks": peaks},
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _run_settings_dict(run: TranscriptionRun) -> Dict[str, Any]:
    """Change 094: Settings-Snapshot eines Runs als Dict."""
    return {
        "enable_vad": run.enable_vad,
        "enable_diarize": run.enable_diarize,
        "diarize_num_speakers": run.diarize_num_speakers,
        "diarize_min_duration_off": run.diarize_min_duration_off,
        "diarize_method": run.diarize_method,
        "enable_streaming": run.enable_streaming,
        "enable_noise_reduce": run.enable_noise_reduce,
        "enable_enhance": run.enable_enhance,
        "enable_punctuation": run.enable_punctuation,
        "enable_llm_enhance": run.enable_llm_enhance,
        "prompt_template_id": run.prompt_template_id,
        "llm_endpoint_id": run.llm_endpoint_id,
    }


@router.get("/recordings/{rid}/runs")
def list_runs_endpoint(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 094: Transkriptionsläufe einer Aufnahme, neueste zuerst.

    Jeder Run trägt den Settings-Snapshot + Status des Laufs — die
    versionierte Antwort auf „welche Version entstand mit welchen
    Einstellungen?". Owner/Admin only (read).
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    runs = session.exec(
        select(TranscriptionRun)
        .where(TranscriptionRun.rec_id == rec.id)
        .order_by(TranscriptionRun.id.desc())
    ).all()
    run_ids = [r.id for r in runs]
    results = session.exec(
        select(TranscriptionResult).where(TranscriptionResult.run_id.in_(run_ids))
    ).all() if run_ids else []
    by_run: Dict[int, TranscriptionResult] = {res.run_id: res for res in results}
    return {
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "backend": r.backend,
                "language": r.language,
                "settings": _run_settings_dict(r),
                "error": r.error,
                "duration_s": r.duration_s,
                "progress_pct": r.progress_pct,
                "phase": r.phase,
                "started_at": iso_utc(r.started_at),
                "finished_at": iso_utc(r.finished_at),
                "created_by_user_id": r.created_by_user_id,
                "result_id": by_run[r.id].id if r.id in by_run else None,
                "segment_count": len(by_run[r.id].segments or []) if r.id in by_run else 0,
            }
            for r in runs
        ]
    }


@router.get("/recordings/{rid}/runs/{run_id}")
def get_run_endpoint(
    rid: str,
    run_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 094: Run-Detail mit vollem Ergebnis (Text + Segmente)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))
    run = session.get(TranscriptionRun, run_id)
    if run is None or run.rec_id != rec.id:
        raise HTTPException(status_code=404, detail="run not found")
    results = session.exec(
        select(TranscriptionResult)
        .where(TranscriptionResult.run_id == run.id)
        .order_by(TranscriptionResult.id.asc())
    ).all()
    return {
        "id": run.id,
        "rec_id": run.rec_id,
        "status": run.status,
        "backend": run.backend,
        "language": run.language,
        "settings": _run_settings_dict(run),
        "error": run.error,
        "duration_s": run.duration_s,
        "progress_pct": run.progress_pct,
        "phase": run.phase,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
        "created_by_user_id": run.created_by_user_id,
        "results": [
            {
                "id": x.id,
                "text": x.text,
                "segments": x.segments or [],
                "created_by_user_id": x.created_by_user_id,
                "created_at": iso_utc(x.created_at),
            }
            for x in results
        ],
    }


class AnonLinkUpdate(BaseModel):
    enabled: bool


@router.post("/recordings/{rid}/anon-link")
def toggle_anon_link(
    rid: str,
    body: AnonLinkUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Anon-Share-Link an/aus (read-only). Nur der Owner (full) darf.

    ``shared_at`` wird beim ERSTEN Aktivieren gesetzt und bleibt auch bei
    Deaktivieren/Reaktivieren erhalten — die Versions-Gating-Basis.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))
    rec.share_token = body.enabled
    if body.enabled and rec.shared_at is None:
        rec.shared_at = dt.datetime.now(dt.timezone.utc)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    # Link-Gültigkeit für die Retention-Warnung im Frontend:
    # expires_at = shared_at + Anon-Retention (der Sweep löscht danach alles).
    ret_min = settings.POLYSCHNACK_ANON_RETENTION_MINUTES
    expires = None
    if rec.share_token and rec.shared_at is not None:
        expires = rec.shared_at + dt.timedelta(minutes=ret_min)
    return {
        "share_token": rec.share_token,
        "shared_at": iso_utc(rec.shared_at) if rec.shared_at else None,
        "retention_minutes": ret_min,
        "expires_at": iso_utc(expires) if expires else None,
    }


# ---------------------------------------------------------------------------
# Audio streaming
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/audio")
def get_audio(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Stream the stored audio file with Range request support."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))

    path = Path(rec.stored_path)
    if not path.exists():
        # Change 014: klare Message statt stiller Fehlerspirale — die GUI
        # zeigt den Defekt-Badge (status=failed) und macht Delete prominent.
        raise HTTPException(
            status_code=410,
            detail="Audio-Datei fehlt oder ist beschädigt",
        )

    mime = _guess_mime(rec.stored_path, rec.mime)
    return FileResponse(
        str(path),
        media_type=mime,
        filename=rec.original_name,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/recordings/{rid}/audio/preview")
def get_audio_preview(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Stream die schlanke Playback-Preview (64-kbps-MP3-Sidecar).

    Der WaveSurfer-Player lädt NUR diese kleine Datei fürs Playback —
    WebAudio müsste sonst die komplette WAV dekodieren (60 min =
    Minuten bis Play). Fehlt die Preview (noch nicht generiert), fällt
    das Frontend auf die volle Audio-URL zurück.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read", cap=_key_cap(request, session))

    preview = getattr(rec, "preview_path", None)
    if not preview or not Path(preview).exists():
        # Fix 2026-08-18: Preview synchron nachgenerieren (best-effort).
        # Vorher 410 → das Frontend fiel auf die volle Audio-Datei zurück;
        # bei langen Aufnahmen lud der Player dann die ganze WAV (und der
        # readyFetch parallel ein zweites Mal) → „loading audio“ endlos.
        # Einmalig dauert der Request länger (ffmpeg 64-kbps), danach
        # existiert das Sidecar und alle weiteren Aufrufe sind schlank.
        try:
            from ..peaks import compute_preview_path

            src = Path(rec.stored_path)
            if src.exists():
                generated = compute_preview_path(src)
                if generated and Path(generated).exists():
                    rec.preview_path = str(generated)
                    rec.preview_size_bytes = Path(generated).stat().st_size
                    session.add(rec)
                    session.commit()
                    preview = generated
        except Exception:
            log.exception("preview: synchron generate failed rid=%s", rid)
        if not preview or not Path(preview).exists():
            raise HTTPException(status_code=410, detail="preview not available yet")

    return FileResponse(
        str(preview),
        media_type="audio/mpeg",
        filename=Path(preview).name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# Download (subtitle/transcript export)
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/download")
def download_transcript(
    rid: str,
    request: Request,
    format: str = "txt",
    max_duration_s: Optional[float] = None,
    session: Session = Depends(get_session),
) -> Response:
    """Download the transcription in an export format.

    Change 008: ``format`` ist ein Template-Name aus
    ``DATA_DIR/export_templates/*.json`` — die eingebauten Namen
    ``txt|srt|vtt`` lösen die Standard-Templates auf, eigene Formate
    (YouTube-Transcript, CSV, …) werden durch eine Template-Datei ohne
    Code-Änderung verfügbar. ``max_duration_s`` (Feature 2026-08-15):
    optionale Re-Segmentierung vor dem Export — identisch zur Preview in
    der Transkriptionsansicht (gleiche Funktion, gleiche Ausgabe).
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    # Review 2026-08-15 (P1): fehlender Access-Check — jeder der die uid
    # kennt konnte Transkripte laden, auch nach Widerruf des Share-Links.
    # Gleicher Guard wie alle Nachbar-Routen.
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    # Template laden (404 bei unbekanntem Namen, 500 bei kaputter Datei).
    try:
        tpl = load_template(format, export_templates_dir())
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail=f"unknown export format: {format}")
    except TemplateInvalid as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    stem = Path(rec.original_name).stem
    disposition = f'attachment; filename="{stem}.{tpl["extension"]}"'

    segments = rec.segments or []
    if max_duration_s is not None and max_duration_s > 0:
        segments = resegment_by_duration(segments, max_duration_s)

    meta = {
        "title": stem,
        "media_file_name": stem,
        "media_file_name_with_ext": rec.original_name,
        "text": rec.text or "",
    }
    content = render_template(tpl, segments, meta)

    ext = tpl["extension"].lower()
    media_type = _EXPORT_MEDIA_TYPES.get(ext, "application/octet-stream")

    # Change 015 (2026-08-18): explizites Encoding — utf-8-sig (BOM) für
    # Text-Formate (Notepad/Excel erkennen Umlaute), reines utf-8 für JSON.
    # Der frühere charset-Header (Fix 2026-08-15) bleibt zusätzlich erhalten.
    return Response(
        content=_encode_export(content, ext),
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


@router.get("/recordings/{rid}/backup")
def backup_download(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """Vollständiger Backup-Download (Change 015): ZIP mit transcript.json
    (Schema v1 inkl. Word-Timings + Versionen), Audio, txt/srt + manifest.

    Zugriff ``full`` (Owner oder Share mit full), Status muss ``done`` sein.
    Datenschutz: Backups enthalten keine DB-internen IDs; anon-Recordings
    vermerken ``retention_minutes`` im JSON.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    if rec.id is None:  # Pyright-Guard (DB-Rows haben immer eine id)
        raise HTTPException(status_code=404, detail="not found")
    versions = list_versions(session, rec.id)
    zip_bytes = build_backup_zip(session, rec, versions)

    stem = Path(rec.original_name).stem
    disposition = f'attachment; filename="{stem}-backup.zip"'
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.post("/recordings/import-backup")
def import_backup_ep(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Backup-ZIP importieren (Change 015): stellt ein Recording mit
    status=done wieder her — Audio, Titel, Segmente inkl. Word-Timings,
    Einstellungen und Versions-Snapshots. Keine Neu-Transkription.

    Validierung: manifest.json (SHA-256 je Datei) + schema_version.
    Duplikat-Erkennung über content_hash wie beim Upload (409).
    anon-Import unterliegt den normalen anon-Limits (Retention ab Import).
    """
    uid = _current_user(request, session)
    from ..anon_limits import enforce_anon_limits

    anon_user = session.get(User, uid) if uid is not None else None
    anon = anon_user is None or anon_user.kind == "anonymous"
    try:
        raw = file.file.read()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Upload nicht lesbar: {exc}")

    # anon-Limits: Größe des ZIP ≈ Größe des enthaltenen Audios.
    try:
        enforce_anon_limits(session, anon_user, len(raw), duration_s=None)
    except HTTPException:
        raise

    from ..export_backup import BackupError, import_backup_zip

    # Duplikat-Vorprüfung NICHT hier (import_backup_zip rechnet den
    # content_hash aus dem Audio) — Fehler → 400, Duplikat → 409.
    try:
        rec = import_backup_zip(
            session,
            raw,
            user_id=uid,
            audio_dir=settings.AUDIO_DIR,
            anon=anon,
        )
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Duplikat (content_hash existiert schon) → 409 wie beim Upload.
    dup = session.exec(
        select(Recording).where(
            Recording.content_hash == rec.content_hash,
            Recording.id != rec.id,
        )
    ).first()
    if dup is not None:
        # Das gerade importierte Recording wieder entfernen (Datei + Row) —
        # es war ein Duplikat, der User bekommt den bestehenden Eintrag.
        try:
            Path(rec.stored_path).unlink(missing_ok=True)
        except OSError:
            pass
        from ..crud import delete_recording

        delete_recording(session, rec.id)
        raise HTTPException(
            status_code=409,
            detail={
                "duplicate": True,
                "existing_id": dup.uid,
                "recording": _recording_to_dict(dup, session=session),
            },
        )

    if rec.id is not None:
        _schedule_peaks(rec.id)  # Waveform-Preview sofort rechnen
    return _recording_to_dict(rec, session=session)


@router.get("/export-templates")
def export_templates_ep(session: Session = Depends(get_session)) -> dict:
    """Liste aller verfügbaren Export-Templates (Name + Endung) für das
    UI-Dropdown (Change 008)."""
    return {"templates": list_templates(export_templates_dir())}


# ---------------------------------------------------------------------------
# Transcribe (start manually)
# ---------------------------------------------------------------------------


@router.post("/recordings/{rid}/transcribe")
def transcribe_ep(
    rid: str,
    request: Request,
    enable_vad: Optional[bool] = Form(None),
    vad_mode: Optional[str] = Form(None),  # Change 114: off|edges|all
    enable_diarize: Optional[bool] = Form(None),
    diarize_num_speakers: Optional[int] = Form(None),
    diarize_min_duration_off: Optional[float] = Form(None),
    diarize_method: Optional[str] = Form(None),
    enable_streaming: Optional[bool] = Form(None),
    enable_noise_reduce: Optional[bool] = Form(None),
    enable_enhance: Optional[str] = Form(None),
    separate_backend: Optional[str] = Form(None),  # Change 106
    enable_punctuation: Optional[bool] = Form(None),
    enable_llm_enhance: Optional[bool] = Form(None),
    prompt_template_id: Optional[int] = Form(None),
    delivery_target_id: Optional[int] = Form(None),
    llm_endpoint_id: Optional[int] = Form(None),
    backend: str = Form(""),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Queue a transcription for an uploaded recording (Task 6)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(
        session, rec, uid, "full",
        cap=_key_cap(request, session),
        is_admin=_is_admin_session(request),
    )

    _ensure_audio_present(rec)   # 410 statt 500 bei fehlender Datei

    from ..pricing import ensure_free_only

    user = session.get(User, uid) if uid is not None else None
    ensure_free_only(
        user,
        backend or settings.POLYSCHNACK_DEFAULT_BACKEND,
        want_llm=bool(enable_llm_enhance) or prompt_template_id is not None
        or llm_endpoint_id is not None,
        llm_mode=bool(enable_punctuation)
        and settings.POLYSCHNACK_PUNCTUATION_MODE == "llm",
    )

    # Change 099: Settings in den queued-Run (versionierte Wahrheit) — das
    # Recording trägt keine Settings-Spalten mehr. Existiert ein queued-Run
    # (vom Upload), werden DESSEN Settings aktualisiert; sonst neuer Run.
    # Direkte Funktionsaufrufe (Tests) liefern Form(...)-Objekte statt Werten.
    if not isinstance(separate_backend, (str, type(None))):
        separate_backend = None
    # Change 121: Nur EXPLIZIT gesendete Felder überschreiben — None = „nicht
    # gesendet" → bestehenden Run-Wert behalten (bzw. Modell-Default für neue
    # Runs). Vorher wurden fehlende Felder still auf Form-Defaults gesetzt
    # (stiller Fail für API-Clients, die nach dem Upload nur transcribe
    # aufrufen und ihre Upload-Auswahl verloren). Das Frontend sendet immer
    # alle Felder → Browser-Verhalten unverändert.
    if not isinstance(enable_vad, (bool, type(None))):
        enable_vad = None
    if not isinstance(enable_diarize, (bool, type(None))):
        enable_diarize = None
    if not isinstance(enable_streaming, (bool, type(None))):
        enable_streaming = None
    if not isinstance(enable_noise_reduce, (bool, type(None))):
        enable_noise_reduce = None
    if not isinstance(vad_mode, (str, type(None))):
        vad_mode = None
    if not isinstance(enable_enhance, (str, type(None))):
        enable_enhance = None
    from ..models import (DeliveryTarget, PromptTemplate, TranscriptionRun,
                          UserLlmEndpoint)
    from sqlmodel import select as _select

    run = session.exec(_select(TranscriptionRun).where(
        TranscriptionRun.rec_id == rec.id,
        TranscriptionRun.status == "queued",
    ).order_by(TranscriptionRun.id.asc())).first()
    if run is None:
        run = TranscriptionRun(
            rec_id=rec.id, status="queued", created_by_user_id=uid)
        session.add(run)
        # Modell-Defaults für neue Runs (bisherige Form-Defaults)
        if enable_vad is None:
            enable_vad = False
        if vad_mode is None:
            vad_mode = "off"
        if enable_diarize is None:
            enable_diarize = False
        if enable_streaming is None:
            enable_streaming = False
        if enable_noise_reduce is None:
            enable_noise_reduce = True
        if enable_enhance is None:
            enable_enhance = "off"
        if separate_backend is None:
            separate_backend = "none"
    # VAD: explizit gesendetes vad_mode gewinnt; nur enable_vad → Ableitung
    if vad_mode is not None and vad_mode in ("off", "edges", "all"):
        run.vad_mode = vad_mode
    elif enable_vad is not None:
        if enable_vad:
            run.vad_mode = run.vad_mode if run.vad_mode in ("edges", "all") else "edges"
        else:
            run.vad_mode = "off"
    if enable_vad is not None:
        run.enable_vad = enable_vad
    if vad_mode is not None and vad_mode in ("off", "edges", "all") and enable_vad is None:
        run.enable_vad = vad_mode != "off"  # Change 114: konsistente Ableitung
    if run.vad_mode == "off" and run.enable_vad:
        run.vad_mode = "edges"  # Change 114: alter Client sendet nur enable_vad=true
        run.enable_vad = True
    if enable_diarize is not None:
        run.enable_diarize = enable_diarize
    if diarize_num_speakers is not None:
        run.diarize_num_speakers = diarize_num_speakers
    if diarize_min_duration_off is not None:
        run.diarize_min_duration_off = diarize_min_duration_off
    if diarize_method is not None:
        run.diarize_method = diarize_method
    if enable_streaming is not None:
        run.enable_streaming = enable_streaming
    if enable_noise_reduce is not None:
        run.enable_noise_reduce = enable_noise_reduce
    if enable_enhance is not None:
        run.enable_enhance = enable_enhance
    if separate_backend is not None:
        run.separate_backend = separate_backend  # Change 106 (Fix 23.08.)
    if enable_punctuation is not None:
        run.enable_punctuation = enable_punctuation
    if enable_llm_enhance is not None:
        run.enable_llm_enhance = enable_llm_enhance
    if backend:
        run.backend = backend

    if prompt_template_id is not None:
        tpl = session.get(PromptTemplate, prompt_template_id)
        if tpl is None or tpl.user_id != uid:
            raise HTTPException(status_code=403, detail="template not found or not yours")
        run.prompt_template_id = prompt_template_id
    if delivery_target_id is not None:
        tgt = session.get(DeliveryTarget, delivery_target_id)
        if tgt is None or tgt.user_id != uid:
            raise HTTPException(status_code=403, detail="target not found or not yours")
        run.delivery_target_id = delivery_target_id
        rec.delivery_status = "pending"
    if llm_endpoint_id is not None:
        ep = session.get(UserLlmEndpoint, llm_endpoint_id)
        if ep is None or ep.user_id != uid:
            raise HTTPException(status_code=403, detail="endpoint not found or not yours")
        run.llm_endpoint_id = llm_endpoint_id
    session.add(run)
    session.flush()  # Change 099: run.id belegen, bevor der Zeiger ihn nutzt
    session.add(rec)
    prev_run_id = rec.current_run_id  # Change 143: Rollback-Ziel bei enqueue-Fehlern
    if rec.current_run_id is None:
        rec.current_run_id = run.id  # Change 099: Zeiger auf den aktiven Run
    session.commit()

    backend = backend or settings.POLYSCHNACK_DEFAULT_BACKEND
    # Nicht-Default-Backends: Anon nur wenn laufend, Admin → Auto-Start (409/503 sonst)
    ensure_backend_available(backend, request)
    # VRAM-Prognose: zu lange Datei → 409 mit Live-Modus-Hinweis BEVOR es zum OOM kommt
    _check_long_audio(backend, rec)
    try:
        position = queue_manager.enqueue(
            int(rec.id), uid, backend,
            priority=1 if (user is not None and user.kind == "anonymous") else 0,
        )
    except QueueFullError as exc:
        _abort_queued_run(session, rec, run, prev_run_id)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
        _abort_queued_run(session, rec, run, prev_run_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_peaks(int(rec.id))  # Alt-Aufnahmen ohne Peaks: Wellenform beim Transcribe nachziehen
    return {"id": rid, "status": "queued", "position": position, "backend": backend}


# ---------------------------------------------------------------------------
# Re-transcribe
# ---------------------------------------------------------------------------


class RetranscribeParams(BaseModel):
    enable_vad: bool = False
    vad_mode: str = "off"  # Change 114: off|edges|all
    enable_diarize: bool = False
    diarize_num_speakers: Optional[int] = None
    diarize_min_duration_off: Optional[float] = None
    diarize_method: Optional[str] = None
    enable_streaming: bool = False
    enable_noise_reduce: bool = True
    enable_enhance: str = "off"
    separate_backend: str = "none"  # Change 106
    enable_punctuation: Optional[bool] = None
    enable_llm_enhance: Optional[bool] = None
    prompt_template_id: Optional[int] = None
    delivery_target_id: Optional[int] = None
    llm_endpoint_id: Optional[int] = None
    backend: str = ""


@router.post("/recordings/{rid}/retranscribe")
def retranscribe(
    rid: str,
    params: RetranscribeParams = RetranscribeParams(),
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Reset transcription state, update settings, and re-queue for processing."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(
        session, rec, uid, "full",
        cap=_key_cap(request, session),
        is_admin=_is_admin_session(request),
    )

    # Change 123: Aufnahme ohne Audiodatei darf nicht still enqueued werden
    # (Worker failt ohne verwertbare Meldung) — 410 mit klarer Meldung,
    # konsistent mit transcribe/duplicate (Self-Healing).
    _ensure_audio_present(rec)

    from ..pricing import ensure_free_only

    user = session.get(User, uid) if uid is not None else None
    ensure_free_only(
        user,
        params.backend or settings.POLYSCHNACK_DEFAULT_BACKEND,
        want_llm=bool(params.enable_llm_enhance) or params.prompt_template_id is not None
        or params.llm_endpoint_id is not None,
        llm_mode=bool(params.enable_punctuation)
        and settings.POLYSCHNACK_PUNCTUATION_MODE == "llm",
    )

    # Change 099: retranscribe legt IMMER einen neuen Run an (versionierte
    # Settings + Historie) — das Recording trägt keine Settings-Spalten.
    from ..models import (DeliveryTarget, PromptTemplate, TranscriptionRun,
                          UserLlmEndpoint)

    run = TranscriptionRun(
        rec_id=rec.id, status="queued", created_by_user_id=uid)
    run.enable_vad = params.enable_vad
    run.vad_mode = (params.vad_mode if params.vad_mode in ("off", "edges", "all")
                    else ("edges" if params.enable_vad else "off"))  # Change 114
    if run.vad_mode == "off" and params.enable_vad:
        run.vad_mode = "edges"  # Change 114: alter Client sendet nur enable_vad=true
    run.enable_vad = run.vad_mode != "off"  # Change 114: konsistente Ableitung
    run.enable_diarize = params.enable_diarize
    run.diarize_num_speakers = params.diarize_num_speakers
    run.diarize_min_duration_off = params.diarize_min_duration_off
    run.diarize_method = params.diarize_method  # Bugfix 2026-08-15: Methode wurde nie persistiert
    run.enable_streaming = params.enable_streaming
    run.enable_noise_reduce = params.enable_noise_reduce
    run.enable_enhance = params.enable_enhance
    run.separate_backend = params.separate_backend  # Change 106 (Fix 23.08.)
    if params.enable_punctuation is not None:
        run.enable_punctuation = params.enable_punctuation
    if params.enable_llm_enhance is not None:
        run.enable_llm_enhance = params.enable_llm_enhance
    if params.backend:
        run.backend = params.backend

    if params.prompt_template_id is not None:
        tpl = session.get(PromptTemplate, params.prompt_template_id)
        if tpl is None or tpl.user_id != uid:
            raise HTTPException(status_code=403, detail="template not found or not yours")
        run.prompt_template_id = params.prompt_template_id
    if params.delivery_target_id is not None:
        tgt = session.get(DeliveryTarget, params.delivery_target_id)
        if tgt is None or tgt.user_id != uid:
            raise HTTPException(status_code=403, detail="target not found or not yours")
        run.delivery_target_id = params.delivery_target_id
        rec.delivery_status = "pending"
    if params.llm_endpoint_id is not None:
        ep = session.get(UserLlmEndpoint, params.llm_endpoint_id)
        if ep is None or ep.user_id != uid:
            raise HTTPException(status_code=403, detail="endpoint not found or not yours")
        run.llm_endpoint_id = params.llm_endpoint_id
    session.add(run)
    session.flush()  # Change 099: run.id belegen, bevor der Zeiger ihn nutzt
    prev_run_id = rec.current_run_id  # Change 143: Rollback-Ziel bei enqueue-Fehlern
    rec.current_run_id = run.id  # Change 099: neuer Run = aktiver Run
    session.add(rec)
    session.commit()

    backend = params.backend or settings.POLYSCHNACK_DEFAULT_BACKEND
    # Nicht-Default-Backends: Anon nur wenn laufend, Admin → Auto-Start (409/503 sonst)
    ensure_backend_available(backend, request)
    # VRAM-Prognose: zu lange Datei → 409 mit Live-Modus-Hinweis BEVOR es zum OOM kommt
    _check_long_audio(backend, rec)
    try:
        position = queue_manager.enqueue(
            int(rec.id), uid, backend,
            priority=1 if (user is not None and user.kind == "anonymous") else 0,
        )
    except QueueFullError as exc:
        _abort_queued_run(session, rec, run, prev_run_id)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
        _abort_queued_run(session, rec, run, prev_run_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_peaks(int(rec.id))  # Alt-Aufnahmen ohne Peaks: Wellenform beim Re-Transcribe nachziehen
    return {"id": rid, "status": "queued", "position": position, "backend": backend}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/recordings/{rid}")
def delete_recording_endpoint(
    rid: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Delete the database row and the audio file from disk."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(
        session, rec, uid, "full",
        cap=_key_cap(request, session),
        is_admin=_is_admin_session(request),
    )
    rec = delete_recording(session, rec.id)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    path = Path(rec.stored_path)
    path.unlink(missing_ok=True)
    # Playback-Preview-Sidecar mitlöschen (falls vorhanden)
    prev = getattr(rec, "preview_path", None)
    if prev:
        Path(prev).unlink(missing_ok=True)
    # Change 014: Sidecar-Metadaten mitlöschen (falls vorhanden)
    try:
        from ..audio_utils import sidecar_path

        sidecar_path(rec.stored_path).unlink(missing_ok=True)
    except Exception:
        pass
    return {"deleted": rid}


class TitleBody(BaseModel):
    title: str


@router.patch("/recordings/{rid}/title")
def set_recording_title(
    rid: str,
    body: TitleBody,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 014: Editierbaren Titel setzen (Owner/Admin).

    Schreibt die DB (Quelle der Wahrheit) und spiegelt title/original_name
    in das Sidecar-JSON neben der Audio-Datei (best-effort) — die
    Dateinamen-Verknüpfung überlebt damit DB-Resets und wandert mit der
    Datei.
    """
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Titel darf nicht leer sein")
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(
        session, rec, uid, "full",
        cap=_key_cap(request, session),
        is_admin=_is_admin_session(request),
    )
    rec.title = title
    rec.updated_at = dt.datetime.now(dt.timezone.utc)  # Change 054: „Last edit date"
    session.add(rec)
    session.commit()
    session.refresh(rec)
    try:
        write_sidecar(rec.stored_path, rec.title, rec.original_name)
    except Exception:
        pass  # best-effort — DB bleibt die Wahrheit
    return {"uid": rec.uid, "title": rec.title, "original_name": rec.original_name}


# ---------------------------------------------------------------------------
# Tags (Change 054)
# ---------------------------------------------------------------------------


class TagsBody(BaseModel):
    tags: List[str] = []


@router.patch("/recordings/{rid}/tags")
def set_recording_tags(
    rid: str,
    body: TagsBody,
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 054: Tags einer Aufnahme setzen (write-Zugriff wie Segment-Edit).

    - dedup + trim; leere Einträge verworfen
    - max. 20 Tags, je max. 40 Zeichen (sonst 400)
    - aktualisiert ``updated_at`` (zählt als Bearbeitung → „Last edit date")
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(
        session, rec, uid, "write",
        cap=_key_cap(request, session),
        is_admin=_is_admin_session(request),
    )
    clean: List[str] = []
    for t in body.tags or []:
        t = str(t).strip()
        if not t:
            continue
        if len(t) > 40:
            raise HTTPException(status_code=400, detail=f"Tag zu lang: {t[:40]}…")
        # Case-insensitives Dedup: „Walzen" und „walzen" sind dasselbe Label;
        # die erste Schreibweise gewinnt.
        if not any(t.lower() == existing.lower() for existing in clean):
            clean.append(t)
        if len(clean) > 20:
            raise HTTPException(status_code=400, detail="max. 20 Tags pro Aufnahme")
    rec.tags = clean
    rec.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"uid": rec.uid, "tags": list(rec.tags or [])}


@router.get("/tags")
def list_all_tags(
    request: Request,
    session: Session = Depends(get_session),
) -> List[str]:
    """Change 092: Alle Tags des aktuellen Users über alle Aufnahmen
    (dedup case-insensitiv, sortiert) — Vorschlagsliste für den
    TagEditor-Autocomplete.

    Konsistente Normalisierung wie PATCH: getrimmt, erste Schreibweise
    gewinnt, leere Einträge verworfen. Nur eigene Aufnahmen (User-Isolation).
    """
    uid = _current_user(request, session)
    seen: set[str] = set()
    out: List[str] = []
    for (rec_tags,) in session.execute(
        select(Recording.tags).where(Recording.user_id == uid)
    ).all():
        for t in rec_tags or []:
            t = str(t).strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return sorted(out, key=str.lower)


# ---------------------------------------------------------------------------
# Crop / transcribe-range
# ---------------------------------------------------------------------------


def _abort_queued_run(session: Session, rec: Any, run: Any, prev_run_id: Optional[int]) -> None:
    """Change 143: Ein committeter, aber nie enqueueder Run darf nicht als
    'queued' verwaist in der DB hängen — sonst zeigt die UI dauerhaft „in
    Warteschlange" und kein Worker startet ihn (User-Befund 2026-08-28).
    Bei enqueue-Fehlern (QueueError/QueueFullError) wird der Run auf
    'failed' gesetzt und der Run-Zeiger auf den vorherigen Stand zurück-
    gerollt (nur wenn er auf den neuen Run zeigt)."""
    run.status = "failed"
    if rec.current_run_id == run.id:
        rec.current_run_id = prev_run_id
    session.add(run)
    session.add(rec)
    session.commit()


@router.post("/recordings/{rid}/transcribe-range", status_code=201)
def transcribe_range(
    rid: str,
    start_sec: float,
    end_sec: float,
    request: Request = None,
    session: Session = Depends(get_session),
):
    """Crop audio to [start_sec, end_sec] and transcribe the segment as a new recording."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

    audio_bytes = Path(rec.stored_path).read_bytes()
    trimmed = trim_audio(audio_bytes, start_sec, end_sec)

    crop_path = storage_path_for(uid, ".wav", anon=_is_anon_user(session, uid))
    crop_path.write_bytes(trimmed)

    from ..service import _current_run
    src_run = _current_run(session, rec)  # Change 099: Settings aus dem Run
    new_rec = create_recording(
        session,
        original_name=f"crop_{start_sec:.0f}s-{end_sec:.0f}s_{rec.original_name}",
        stored_path=str(crop_path),
        mime="audio/wav",
        size_bytes=len(trimmed),
        batch_id=rec.batch_id,
        user_id=uid,
    )
    # Change 099: Settings des Quell-Recordings in den queued-Run des Crops.
    run = create_queued_run(
        session, new_rec.id,
        backend=src_run.backend if src_run else "ps-pk-onnx",
        enable_vad=bool(src_run and src_run.enable_vad),
        vad_mode=_effective_vad_mode(src_run),  # Change 114
        enable_diarize=bool(src_run and src_run.enable_diarize),
        enable_noise_reduce=True if src_run is None else bool(src_run.enable_noise_reduce),
        enable_enhance="off" if src_run is None else (src_run.enable_enhance or "off"),
        separate_backend="none" if src_run is None else (src_run.separate_backend or "none"),  # Change 106
        user_id=uid,
    )
    new_rec.current_run_id = run.id
    session.add(new_rec)
    session.commit()
    return _recording_to_dict(new_rec, session=session)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def stats_endpoint(
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Aggregate counts and totals across all recordings."""
    # Session MUSS übergeben werden: _current_user ohne session crasht in
    # ensure_anonymous_user (AttributeError 'NoneType' has no attribute 'add').
    uid = _current_user(request, session) if settings.OIDC_ENABLED else None
    return get_stats(session, user_id=uid)