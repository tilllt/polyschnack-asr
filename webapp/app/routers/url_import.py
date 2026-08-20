"""POST /api/recordings/from-url — download audio from a URL via yt-dlp."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlmodel import Session, select

from ..audio_utils import original_path, prepare_storage, probe_duration_path, storage_path_for
from ..config import settings
from ..crud import create_recording
from ..db import get_session
from ..docker_proxy import DockerProxyClient, DockerProxyError, get_docker_client
from ..llm_url import validate_llm_url
from ..models import Recording
from .recordings import _current_user, _is_anon_user, _recording_to_dict, _schedule_peaks

log = logging.getLogger(__name__)

#: Kanonische MIME-Typen für die von yt-dlp/extrahierbaren Audio-Formate.
_AUDIO_MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".webm": "audio/webm", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".flac": "audio/flac", ".mpeg": "audio/mpeg",
    ".mp4": "audio/mp4", ".oga": "audio/ogg", ".wma": "audio/x-ms-wma",
}

# ────────────────────────────────────────────────────────────────────
# Change 043: Tor-Fallback (letzte Stufe der Download-Kaskade)
# ────────────────────────────────────────────────────────────────────

#: Bot-Schutz-Signaturen, die den Tor-Fallback auslösen (nur wenn
#: POLYSCHNACK_TOR_FALLBACK=on). yt-dlp-Fehlermeldungen variieren je nach
#: YouTube-Client — deshalb mehrere Muster, alle case-insensitive.
_TOR_BOT_SIGNATURES = (
    "sign in to confirm",
    "http error 403",
    "http error 400",
    "nsig extraction failed",
    "confirm you're not a bot",
    "requested format is not available",
)

#: Container-Name des Tor-Sidecars (compose.backends.yml, Profil ps-tor).
_TOR_CONTAINER = "ps-tor"

#: In-Memory Rate-Limit-Store: user_id → Liste der Download-Timestamps (epoch s).
#: Rolling Window pro User. Prozess-lokal — nach Webapp-Neustart zurückgesetzt
#: (bewusst simpel; ein persistentes Limit wäre für 2/h überdimensioniert).
_tor_usage: Dict[str, List[float]] = {}

#: Globale sequenzielle Queue: max. 1 Tor-Download gleichzeitig (Tor-Circuits
#: sind langsam; parallele Downloads würden die Exit-IPs überlasten).
#: Loop-keyed: asyncio.Lock ist an den Event-Loop gebunden; uvicorn hat genau
#: einen Loop (= ein globales Lock), Tests (asyncio.run) je einen eigenen.
_tor_locks: Dict[int, "asyncio.Lock"] = {}


def _tor_lock() -> "asyncio.Lock":
    loop = asyncio.get_running_loop()
    lock = _tor_locks.get(id(loop))
    if lock is None:
        lock = asyncio.Lock()
        _tor_locks[id(loop)] = lock
    return lock


def _is_bot_block(stderr: str) -> bool:
    """True, wenn yt-dlp-Stderr eine Bot-Schutz-Signatur enthält."""
    low = (stderr or "").lower()
    return any(sig in low for sig in _TOR_BOT_SIGNATURES)


def _tor_rate_limit_allowed(user_id: str, now: Optional[float] = None) -> Tuple[bool, int]:
    """Rate-Limit-Check: max. ``POLYSCHNACK_TOR_MAX_PER_HOUR`` Downloads/h/User.

    Returns ``(allowed, retry_after_s)`` — bei ``allowed=False`` ist
    ``retry_after_s`` die Sekunden bis zum ältesten abgelaufenen Slot.
    """
    limit = settings.POLYSCHNACK_TOR_MAX_PER_HOUR
    if limit <= 0:
        return True, 0
    now = now if now is not None else time.time()
    window = 3600.0
    ts = _tor_usage.get(user_id) or []
    # Abgelaufene Slots entfernen (rolling window).
    ts = [t for t in ts if now - t < window]
    if len(ts) < limit:
        return True, 0
    oldest = min(ts)
    retry_after = max(1, int(window - (now - oldest)))
    return False, retry_after


def _tor_record_usage(user_id: str) -> None:
    """Download-Slot für einen User vermerken (rolling window)."""
    now = time.time()
    ts = _tor_usage.get(user_id) or []
    ts = [t for t in ts if now - t < 3600.0]
    ts.append(now)
    _tor_usage[user_id] = ts


async def _tor_ensure_running(proxy: DockerProxyClient) -> None:
    """ps-tor on-demand starten und auf Health warten (Docker-Proxy)."""
    state = proxy.container_state(_TOR_CONTAINER)
    if state is None:
        raise HTTPException(
            status_code=503,
            detail="Tor-Fallback nicht verfügbar: Container 'ps-tor' existiert nicht "
            "(compose-Profil 'ps-tor' nicht gestartet). Bitte Admin kontaktieren.",
        )
    if not state.get("running"):
        try:
            proxy.start(_TOR_CONTAINER)
        except DockerProxyError as exc:
            raise HTTPException(status_code=503, detail=f"Tor-Start fehlgeschlagen: {exc}")
    # Auf Health/Running warten (Bootstrap dauert 10-60 s).
    for _ in range(40):
        st = proxy.container_state(_TOR_CONTAINER) or {}
        health = st.get("health")
        if st.get("running") and (health in (None, "healthy", "")):
            return
        await asyncio.sleep(1.5)
    raise HTTPException(
        status_code=503,
        detail="Tor-Start überschritt das Zeitlimit (Bootstrap >60 s). Bitte später erneut versuchen.",
    )


def _run_ytdlp_proxy(out_template: str, clean_url: str, proxy: str) -> subprocess.CompletedProcess:
    """yt-dlp über einen SOCKS5-Proxy (Remote-DNS via socks5h)."""
    max_size = f"{settings.POLYSCHNACK_TOR_MAX_SIZE_MB}M"
    return subprocess.run(
        [
            "yt-dlp",
            "-f", "ba/b",
            "-x",
            "-o", out_template,
            "--no-playlist",
            "--proxy", proxy,
            "--max-filesize", max_size,
            "--",
            clean_url,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )


async def _tor_fallback_download(
    clean_url: str,
    out_template: str,
    user_id: str,
) -> subprocess.CompletedProcess:
    """Tor-Fallback-Kaskade: on-demand-Start → max. N Circuits → Download.

    Nur aufrufen, wenn der direkte Download mit Bot-Signatur scheiterte.
    Wirft HTTPException (429/503/400) — nie unbehandelte Exceptions.
    """
    if not settings.POLYSCHNACK_TOR_FALLBACK:
        raise HTTPException(status_code=400, detail="yt-dlp failed (Tor-Fallback deaktiviert)")

    # Rate-Limit (Pflicht, User-Entscheidung).
    allowed, retry_after = _tor_rate_limit_allowed(user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Zu viele Tor-Downloads. Bitte in {retry_after} s erneut versuchen.",
            headers={"Retry-After": str(retry_after)},
        )

    # Sequenzielle Queue: nur 1 Tor-Download gleichzeitig.
    async with _tor_lock():
        proxy = get_docker_client()
        await _tor_ensure_running(proxy)
        proxy_url = f"socks5h://{_TOR_CONTAINER}:9050"

        last_err = "no output"
        for attempt in range(1, settings.POLYSCHNACK_TOR_MAX_CIRCUITS + 1):
            log.info("tor-fallback attempt %d/%d for %s", attempt, settings.POLYSCHNACK_TOR_MAX_CIRCUITS, clean_url[:80])
            try:
                proc = await asyncio.to_thread(_run_ytdlp_proxy, out_template, clean_url, proxy_url)
            except subprocess.TimeoutExpired:
                last_err = f"Tor-Download timeout (attempt {attempt})"
                proc = None
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="yt-dlp not installed")
            if proc is not None and proc.returncode == 0:
                _tor_record_usage(user_id)
                return proc
            if proc is not None:
                last_err = (proc.stderr or "no output")[:300]
            # Neuer Circuit: Container-Neustart → neue Exit-IP (Docker-Proxy
            # erlaubt kein SIGHUP — restart ist das äquivalente Signal).
            if attempt < settings.POLYSCHNACK_TOR_MAX_CIRCUITS:
                try:
                    proxy.restart(_TOR_CONTAINER)
                except DockerProxyError as exc:
                    log.warning("tor restart failed: %s", exc)
                await asyncio.sleep(3)

        # Alle Circuits fehlgeschlagen — ehrlicher Fehler + Desktop-Hinweis.
        hint = (
            "Alle Tor-Circuits fehlgeschlagen. Für private Downloads: "
            "yt-dlp auf dem Desktop nutzen (uv tool upgrade yt-dlp), "
            "oder später erneut versuchen."
        )
        raise HTTPException(status_code=400, detail=f"Tor-Download failed: {last_err} — {hint}")


router = APIRouter(prefix="/api")


@router.post("/recordings/from-url", status_code=201)
async def import_from_url(
    request: Request,
    url: str = Form(...),
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
    """Download audio from *url* via yt-dlp (natives Format), save.

    Seit 2026-08-14 wird das von yt-dlp extrahierte Format (m4a/opus/webm/
    mp3) UNKONVERTIERT gespeichert — kein erzwungener WAV-Re-Encode mehr
    (kleinere Dateien, WaveSurfer + ASR kommen mit allen Formaten klar).
    """
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="no URL provided")

    # ── SSRF-Schutz (Review 2026-08-15, P0.1) ──
    # yt-dlp läuft IM CONTAINER-NETZWERK: ohne Validierung könnte die URL
    # interne Hosts ansprechen (docker-proxy, ASR-Container, Cloud-Metadata).
    # https-only + Host-Allowlist via validate_llm_url (private/loopback/
    # link-local werden abgelehnt). Reuse des BYOK-Guards.
    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
        if parsed.scheme != "https":
            raise HTTPException(status_code=422, detail="only https URLs are allowed")
        validate_llm_url(clean_url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid URL: {exc}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "audio.%(ext)s"
        out_template = str(tmp)

        def _run_ytdlp() -> subprocess.CompletedProcess:
            # `--` vor dem Positionsargument: eine URL, die mit `-` beginnt,
            # wird sonst von yt-dlp als Option geparst (Argument-Injection,
            # z.B. --config-location → beliebige Datei-Lesevorgänge).
            return subprocess.run(
                [
                    "yt-dlp",
                    "-f", "ba/b",  # nur Audio-Stream laden (ba=best audio, b=Fallback)
                    "-x",          # extrahieren, natives Format behalten (kein WAV-Zwang)
                    "-o", out_template,
                    "--no-playlist",
                    "--",  # Ende der Optionen
                    clean_url,
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

        def _run_ytdlp_client(client: str) -> subprocess.CompletedProcess:
            """Retry mit alternativem YouTube-Player-Client (Bot-Schutz)."""
            return subprocess.run(
                [
                    "yt-dlp",
                    "-f", "ba/b",
                    "-x",
                    "-o", out_template,
                    "--no-playlist",
                    "--extractor-args", f"youtube:player_client={client}",
                    "--",
                    clean_url,
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

        # Event-Loop-Fix (Review P0.1): yt-dlp + ffmpeg laufen bis zu 600 s
        # synchron — im async-Handler blockiert das JEDEN anderen Request.
        # asyncio.to_thread hält den Loop frei.
        try:
            proc = await asyncio.to_thread(_run_ytdlp)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=400, detail="URL download timed out (10 min)")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="yt-dlp not installed")

        # YouTube blockt Datacenter-IPs intermittierend (Bot-Schutz, flaky 403).
        # Ein Fehlschlag ist meist in <2 s fertig — ein zweiter Versuch hat
        # gute Erfolgschancen und macht den Import spürbar robuster.
        if proc.returncode != 0:
            retry_proc = await asyncio.to_thread(_run_ytdlp)
            if retry_proc.returncode == 0:
                proc = retry_proc

        # Change 041: Bot-Schutz-Persistenz (403 „Sign in to confirm") —
        # zwei identische Versuche reichen nicht. Dann mit alternativen
        # Player-Clients retryen (tv/web_embedded/ios umgehen den Standard-
        # Client-Block, brauchen aber JS-Runtime im Image → nodejs).
        if proc.returncode != 0:
            err = (proc.stderr or "")[:500]
            low = err.lower()
            if "sign in to confirm" in low or "http error 403" in low or "http error 400" in low:
                for client in ("tv", "web_embedded", "ios"):
                    client_proc = await asyncio.to_thread(
                        _run_ytdlp_client, client)
                    if client_proc.returncode == 0:
                        proc = client_proc
                        break

        # Change 043: Tor-Fallback als LETZTE Stufe — nur wenn (a) Bot-Signatur
        # vorliegt, (b) aktiviert, (c) User eingeloggt (anon-Sperre: anon-Sessions
        # bekommen den ressourcenintensiven Tor-Pfad nicht, User-Entscheidung).
        if proc.returncode != 0 and _is_bot_block(proc.stderr or ""):
            current_user_id = _current_user(request, session)
            if _is_anon_user(session, current_user_id):
                # anon → kein Tor-Fallback: verständlicher 400 statt stiller
                # Fehlversuch (die yt-dlp-Originalmeldung folgt unten).
                log.info("tor-fallback skipped for anon user (url=%s)", url[:80])
            elif settings.POLYSCHNACK_TOR_FALLBACK:
                tor_proc = await _tor_fallback_download(
                    clean_url, out_template, str(current_user_id))
                if tor_proc.returncode == 0:
                    proc = tor_proc

        if proc.returncode != 0:
            err = (proc.stderr or "no output")[:500]
            log.warning("yt-dlp failed for url=%s: %s", url[:80], err)
            hint = _ytdlp_error_hint(err, url)
            detail = f"yt-dlp failed: {err}"
            if hint:
                detail += f" — {hint}"
            raise HTTPException(status_code=400, detail=detail)

        # WICHTIG: NICHT auf --print filename verlassen — das druckt den
        # Namen VOR der Audio-Extraktion. Stattdessen suchen wir die erzeugte
        # Datei im Tempdir (Format variiert seit 2026-08-14: m4a/opus/webm/…).
        files = sorted(
            p for p in Path(tmpdir).iterdir()
            if p.is_file() and p.name != "audio.%(ext)s"
        )
        if not files:
            raise HTTPException(status_code=400, detail="yt-dlp produced no audio file")
        src_path = files[0]

        audio_data = src_path.read_bytes()

    if not audio_data:
        raise HTTPException(status_code=400, detail="empty audio downloaded")

    # Storage-Policy: natives Format behalten (Browser/ASR können es), nur
    # exotische Formate → MP3 128k mono. Original-Bytes für Change 018
    # (Export soll das Original liefern) VOR der Konvertierung merken.
    raw_orig = audio_data
    audio_data, new_ext, conv_note = prepare_storage(audio_data, src_path.name)

    content_hash = hashlib.blake2b(audio_data, digest_size=16).hexdigest()
    current_user_id = _current_user(request, session)
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()
    # Dedup NUR innerhalb derselben Identität: eine fremde Recording
    # zurückzugeben würde im Frontend als „Import ok" wirken, aber die
    # Aufnahme gehört einem anderen anon-User → Transcribe schlägt dort
    # mit 403 „requires at least 'full' access" fehl (stiller Fehler).
    if existing and existing.user_id == current_user_id:
        return _recording_to_dict(existing)

    stored = storage_path_for(
        current_user_id, new_ext,
        anon=_is_anon_user(session, current_user_id),
    )
    stored.write_bytes(audio_data)

    # Change 018: Bei echter Transkodierung (Endung geändert) das Original
    # aufbewahren (Export/Backup → audio.original.<ext>).
    orig_ext = Path(src_path.name).suffix.lower() or ".bin"
    if conv_note and orig_ext != new_ext:
        original_path(stored, orig_ext).write_bytes(raw_orig)

    # Exakte Dauer via ffprobe (Basis für VRAM-Prognose + ETA) — Datei-basiert
    est_duration_s = probe_duration_path(stored) or (len(audio_data) / 8000)
    # Kanonisches MIME statt mimetypes (liefert auf manchen Systemen
    # audio/x-wav statt audio/wav — bricht WaveSurfer/ASR nicht, aber Tests)
    mime = _AUDIO_MIME.get(new_ext) or mimetypes.guess_type(stored.name)[0] or "audio/mpeg"

    rec = create_recording(
        session,
        original_name=f"URL: {url[:80]}",
        stored_path=str(stored),
        mime=mime,
        size_bytes=len(audio_data),
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
        user_id=current_user_id,  # session nötig (anon-Identität)
    )
    if rec.id is not None:
        _schedule_peaks(rec.id)  # Waveform-Preview sofort im Hintergrund rechnen
    return _recording_to_dict(rec)


def _ytdlp_error_hint(stderr: str, url: str) -> str | None:
    """Verständlicher Zusatzhinweis für bekannte yt-dlp-Fehlerbilder.

    YouTube blockt Datacenter-IPs regelmäßig mit Bot-Schutz (403/„Sign in
    to confirm you're not a bot"). Der User soll wissen, dass das nicht an
    der App liegt — statt nur den rohen yt-dlp-Text zu sehen.
    """
    low = stderr.lower()
    is_youtube = "youtube" in url.lower() or "youtu.be" in url.lower()
    # Change 041: JS-Runtime fehlt im Image (Node/Deno) → YouTube-Player-
    # Challenge nicht lösbar. Das Image braucht nodejs (Dockerfile).
    if "no supported javascript runtime was found" in low:
        return (
            "yt-dlp kann die YouTube-Player-Challenge nicht lösen — im "
            "Server-Image fehlt ein JavaScript-Runtime (Node.js). Bitte "
            "das Webapp-Image neu bauen (enthält seit Change 041 nodejs)."
        )
    if is_youtube and (
        "sign in to confirm you're not a bot" in low
        or "http error 403" in low
        or "http error 400" in low
        or "video unavailable" in low
    ):
        return (
            "YouTube hat den Download abgelehnt (Bot-Schutz oder "
            "Alters-/Regionsbeschränkung). Bitte später erneut versuchen "
            "oder eine andere Quelle nutzen."
        )
    return None
