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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from ..config import settings
from ..audio_utils import convert_to_wav_16k_mono, prepare_storage, probe_duration_path
from ..crud import (
    create_recording,
    delete_recording,
    get_recording,
    get_recording_by_uid,
    get_stats,
    list_recordings,
)
from ..db import get_session
from ..models import Recording, RecordingShare, User
from ..permissions import ensure_access, get_access_level
from ..queue import QueueError, QueueFullError, queue_manager
from ..service import to_srt, to_txt, to_vtt, trim_audio
from ..whatsapp import parse_whatsapp

router = APIRouter(prefix="/api")

log = __import__("logging").getLogger(__name__)

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
    _peaks_inflight.add(rec_id)
    import threading

    threading.Thread(target=_compute_peaks_background, args=(rec_id,), daemon=True).start()


def _compute_peaks_background(rec_id: int) -> None:
    try:
        from sqlmodel import Session as _Session

        from ..crud import get_recording as _gr
        from ..db import engine as _engine
        from ..service import _compute_peaks_path

        with _Session(_engine) as s:
            rec = _gr(s, rec_id)
            if rec is None or getattr(rec, "waveform_peaks", None):
                return
            # Pfad-basiert (statt read_bytes): 357-MB-Files würden sonst das
            # RAM-Limit sprengen (OOM-Kill, s. peaks.compute_peaks_path).
            peaks = _compute_peaks_path(Path(rec.stored_path))
            if peaks:
                rec.waveform_peaks = peaks
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


def _recording_to_dict(rec: Recording, access_level: Optional[str] = None) -> Dict[str, Any]:
    """Serialise a Recording row to the canonical API response shape."""
    uid = rec.uid or str(rec.id)  # fallback for legacy rows without uid
    return {
        "id": rec.id,
        "uid": uid,
        "original_name": rec.original_name,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "duration_s": rec.duration_s,
        "status": rec.status,
        "text": rec.text,
        "error": rec.error,
        "processing_ms": rec.processing_ms,
        "progress_pct": rec.progress_pct,
        "progress_note": rec.progress_note,
        "created_at": rec.created_at.isoformat(),
        "language": rec.language,
        "segments": rec.segments,
        "audio_url": f"/api/recordings/{uid}/audio",
        "download_url": f"/api/recordings/{uid}/download",
        # WhatsApp / batch fields
        "batch_id": rec.batch_id,
        "recorded_at": rec.recorded_at.isoformat() if rec.recorded_at else None,
        "source": rec.source,
        "enable_vad": rec.enable_vad,
        "enable_diarize": rec.enable_diarize,
        "diarize_num_speakers": rec.diarize_num_speakers,
        "diarize_min_duration_off": rec.diarize_min_duration_off,
        "diarize_method": rec.diarize_method,
        "enable_streaming": rec.enable_streaming,
        "enable_noise_reduce": rec.enable_noise_reduce,
        "enable_enhance": rec.enable_enhance,
        "waveform_peaks": rec.waveform_peaks,
        "updated_at": rec.updated_at.isoformat() if getattr(rec, "updated_at", None) else None,
        "user_id": rec.user_id,
        "access_level": access_level,
        "is_anon_shared": bool(getattr(rec, "share_token", False)),
        "retention_minutes": settings.POLYSCHNACK_ANON_RETENTION_MINUTES,
        "shared_at": rec.shared_at.isoformat() if getattr(rec, "shared_at", None) else None,
        "delivery_status": rec.delivery_status,
        "delivery_error": rec.delivery_error,
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


@router.post("/recordings", status_code=201)
async def upload_recording(
    request: Request,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    diarize_num_speakers: Optional[int] = Form(None),
    diarize_min_duration_off: Optional[float] = Form(None),
    diarize_method: Optional[str] = Form(None),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Accept a multipart audio upload, persist it."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")

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
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()

    # Duplikat nur melden, wenn die Datei des Treffers auch wirklich noch auf
    # der Platte liegt. Sonst (Upload → gelöscht → wieder hochgeladen) wäre
    # der „Upload again"-Kopier-Pfad tot (409 source file missing) — dann
    # legen wir stattdessen einfach ein neues Recording an.
    if (
        existing
        and not (request.query_params.get("force") == "true")
        and Path(existing.stored_path).is_file()
    ):
        return {
            "duplicate": True,
            "existing_id": existing.id,
            "recording": _recording_to_dict(existing),
        }

    # Storage-Policy (2026-08-14): native Formate (MP3/OGG/WebM/…) werden
    # UNKONVERTIERT gespeichert — WaveSurfer (Browser) und die ASR-Backends
    # (ffmpeg-Decode) können sie nativ. Nur exotische Formate → 16-kHz-mono-WAV.
    audio_data, new_ext, conv_note = prepare_storage(raw, file.filename)

    stored = settings.AUDIO_DIR / f"{uuid.uuid4().hex}{new_ext}"
    stored.write_bytes(audio_data)

    recorded_at, source = parse_whatsapp(file.filename)

    # Exakte Dauer via ffprobe — Grundlage für die VRAM-Prognose und die ETA.
    # Datei-basiert (Pipe liefert bei nicht-seekbarem Input oft „N/A"; der
    # alte Größen-Fallback war bei 128-kbps-MP3 um Faktor 2 daneben und
    # hätte Long-Audio-Grenzen/Quota falsch ausgelöst).
    est_duration_s = probe_duration_path(stored) or (len(raw) / 8000)

    # Task B5: harte Limits für anonyme User (Dauer, Upload-Größe, Disk-Quota)
    uid = _current_user(request, session)
    from ..anon_limits import enforce_anon_limits

    enforce_anon_limits(
        session,
        session.get(User, uid) if uid is not None else None,
        len(audio_data),
        est_duration_s,
    )

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
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        diarize_num_speakers=diarize_num_speakers,
        diarize_min_duration_off=diarize_min_duration_off,
        diarize_method=diarize_method,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        content_hash=content_hash,
        user_id=uid,
    )
    if rec.id is not None:
        _schedule_peaks(rec.id)  # Waveform-Preview sofort im Hintergrund rechnen
    return _recording_to_dict(rec)


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

    src = Path(rec.stored_path)
    if not src.is_file():
        raise HTTPException(status_code=409, detail="source file missing")
    new_path = settings.AUDIO_DIR / f"{uuid.uuid4().hex}{src.suffix.lower() or '.bin'}"
    import shutil

    shutil.copy2(src, new_path)

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
        enable_vad=rec.enable_vad,
        enable_diarize=rec.enable_diarize,
        diarize_num_speakers=rec.diarize_num_speakers,
        diarize_min_duration_off=rec.diarize_min_duration_off,
        diarize_method=rec.diarize_method,
        enable_streaming=rec.enable_streaming,
        enable_noise_reduce=rec.enable_noise_reduce,
        enable_enhance=rec.enable_enhance,
        content_hash=rec.content_hash,
        user_id=uid,
    )
    if new_rec.id is not None:
        # Peaks übernehmen statt neu dekodieren — identischer Inhalt, und
        # bei 300+-MB-Dateien wäre der Voll-Decode der OOM-Trigger gewesen.
        new_rec.waveform_peaks = rec.waveform_peaks
        session.add(new_rec)
        session.commit()
    return _recording_to_dict(new_rec)


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
    out_path = settings.AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
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
    return _recording_to_dict(new_rec)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


@router.get("/recordings")
def list_recordings_endpoint(
    q: Optional[str] = None,
    request: Request = None,
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Return all recordings (newest first), optionally filtered by *q*."""
    uid = _current_user(request, session)
    rows = list_recordings(session, q=q, user_id=uid, include_shares=uid is not None)
    # Alt-Aufnahmen ohne Peaks (vor dem Peaks-Feature hochgeladen): Preview im
    # Hintergrund nachziehen, damit die Karte nicht dauerhaft
    # "Waveform data corrupted" zeigt (WaveSurfer muesste sonst die ganze
    # Datei dekodieren).
    for _rec in rows:
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
    for r in rows:
        d = _recording_to_dict(r, access_level=get_access_level(
            session, r, uid, cap=_key_cap(request, session)))
        d["shared_with_me"] = r.user_id != uid and r.id in share_rec_ids
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
        session, rec, uid, cap=_key_cap(request, session)))
    # Visuelle Markierung: "shared_with_me" = fremde Recording via User-Share
    shared_with_me = False
    if uid is not None and rec.user_id != uid:
        shared_with_me = session.exec(
            select(RecordingShare).where(
                RecordingShare.rec_id == rec.id, RecordingShare.user_id == uid
            )
        ).first() is not None
    d["shared_with_me"] = shared_with_me
    # Debug: include word presence info without changing data
    segs = d.get("segments") or []
    d["_words_debug"] = {
        "total_segments": len(segs),
        "segs_with_words": sum(1 for s in segs if s.get("words") and len(s["words"]) > 0),
        "total_words": sum(len(s.get("words") or []) for s in segs),
    }
    return d


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
        "shared_at": rec.shared_at.isoformat() if rec.shared_at else None,
        "retention_minutes": ret_min,
        "expires_at": expires.isoformat() if expires else None,
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
        raise HTTPException(status_code=410, detail="audio file gone")

    mime = _guess_mime(rec.stored_path, rec.mime)
    return FileResponse(
        str(path),
        media_type=mime,
        filename=rec.original_name,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# Download (subtitle/transcript export)
# ---------------------------------------------------------------------------


@router.get("/recordings/{rid}/download")
def download_transcript(
    rid: str,
    format: str = "txt",
    session: Session = Depends(get_session),
) -> Response:
    """Download the transcription as txt, srt, or vtt."""
    if format not in ("txt", "srt", "vtt"):
        raise HTTPException(status_code=400, detail="format must be txt, srt, or vtt")

    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    stem = Path(rec.original_name).stem
    disposition = f'attachment; filename="{stem}.{format}"'

    if format == "txt":
        content = to_txt(rec.text or "")
        media_type = "text/plain"
    elif format == "srt":
        content = to_srt(rec.segments or [])
        media_type = "application/x-subrip"
    else:  # vtt
        content = to_vtt(rec.segments or [])
        media_type = "text/vtt"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


# ---------------------------------------------------------------------------
# Transcribe (start manually)
# ---------------------------------------------------------------------------


@router.post("/recordings/{rid}/transcribe")
def transcribe_ep(
    rid: str,
    request: Request,
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    diarize_num_speakers: Optional[int] = Form(None),
    diarize_min_duration_off: Optional[float] = Form(None),
    diarize_method: Optional[str] = Form(None),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    enable_enhance: str = Form("off"),
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
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

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

    # Update toggle values from the transcribe request (they may have changed since upload)
    rec.enable_vad = enable_vad
    rec.enable_diarize = enable_diarize
    rec.diarize_num_speakers = diarize_num_speakers
    rec.diarize_min_duration_off = diarize_min_duration_off
    rec.diarize_method = diarize_method
    rec.enable_streaming = enable_streaming
    rec.enable_noise_reduce = enable_noise_reduce
    rec.enable_enhance = enable_enhance
    if enable_punctuation is not None:
        rec.enable_punctuation = enable_punctuation
    if enable_llm_enhance is not None:
        rec.enable_llm_enhance = enable_llm_enhance

    from ..models import DeliveryTarget, PromptTemplate, UserLlmEndpoint

    if prompt_template_id is not None:
        tpl = session.get(PromptTemplate, prompt_template_id)
        if tpl is None or tpl.user_id != uid:
            raise HTTPException(status_code=403, detail="template not found or not yours")
        rec.prompt_template_id = prompt_template_id
    if delivery_target_id is not None:
        tgt = session.get(DeliveryTarget, delivery_target_id)
        if tgt is None or tgt.user_id != uid:
            raise HTTPException(status_code=403, detail="target not found or not yours")
        rec.delivery_target_id = delivery_target_id
        rec.delivery_status = "pending"
    if llm_endpoint_id is not None:
        ep = session.get(UserLlmEndpoint, llm_endpoint_id)
        if ep is None or ep.user_id != uid:
            raise HTTPException(status_code=403, detail="endpoint not found or not yours")
        rec.llm_endpoint_id = llm_endpoint_id
    session.add(rec)
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
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_peaks(int(rec.id))  # Alt-Aufnahmen ohne Peaks: Wellenform beim Transcribe nachziehen
    return {"id": rid, "status": "queued", "position": position, "backend": backend}


# ---------------------------------------------------------------------------
# Re-transcribe
# ---------------------------------------------------------------------------


class RetranscribeParams(BaseModel):
    enable_vad: bool = False
    enable_diarize: bool = False
    diarize_num_speakers: Optional[int] = None
    diarize_min_duration_off: Optional[float] = None
    diarize_method: Optional[str] = None
    enable_streaming: bool = False
    enable_noise_reduce: bool = True
    enable_enhance: str = "off"
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
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))

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

    rec.enable_vad = params.enable_vad
    rec.enable_diarize = params.enable_diarize
    rec.diarize_num_speakers = params.diarize_num_speakers
    rec.diarize_min_duration_off = params.diarize_min_duration_off
    rec.enable_streaming = params.enable_streaming
    rec.enable_noise_reduce = params.enable_noise_reduce
    rec.enable_enhance = params.enable_enhance
    if params.enable_punctuation is not None:
        rec.enable_punctuation = params.enable_punctuation
    if params.enable_llm_enhance is not None:
        rec.enable_llm_enhance = params.enable_llm_enhance

    from ..models import DeliveryTarget, PromptTemplate, UserLlmEndpoint

    if params.prompt_template_id is not None:
        tpl = session.get(PromptTemplate, params.prompt_template_id)
        if tpl is None or tpl.user_id != uid:
            raise HTTPException(status_code=403, detail="template not found or not yours")
        rec.prompt_template_id = params.prompt_template_id
    if params.delivery_target_id is not None:
        tgt = session.get(DeliveryTarget, params.delivery_target_id)
        if tgt is None or tgt.user_id != uid:
            raise HTTPException(status_code=403, detail="target not found or not yours")
        rec.delivery_target_id = params.delivery_target_id
        rec.delivery_status = "pending"
    if params.llm_endpoint_id is not None:
        ep = session.get(UserLlmEndpoint, params.llm_endpoint_id)
        if ep is None or ep.user_id != uid:
            raise HTTPException(status_code=403, detail="endpoint not found or not yours")
        rec.llm_endpoint_id = params.llm_endpoint_id
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
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueError as exc:
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
    ensure_access(session, rec, uid, "full", cap=_key_cap(request, session))
    rec = delete_recording(session, rec.id)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    path = Path(rec.stored_path)
    path.unlink(missing_ok=True)
    return {"deleted": rid}


# ---------------------------------------------------------------------------
# Crop / transcribe-range
# ---------------------------------------------------------------------------


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

    stem = Path(rec.stored_path).stem
    parent = Path(rec.stored_path).parent
    crop_path = parent / f"{stem}_crop_{int(start_sec)}-{int(end_sec)}.wav"
    crop_path.write_bytes(trimmed)

    new_rec = create_recording(
        session,
        original_name=f"crop_{start_sec:.0f}s-{end_sec:.0f}s_{rec.original_name}",
        stored_path=str(crop_path),
        mime="audio/wav",
        size_bytes=len(trimmed),
        batch_id=rec.batch_id,
        enable_vad=rec.enable_vad,
        enable_diarize=rec.enable_diarize,
        user_id=uid,
    )
    return _recording_to_dict(new_rec)


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
