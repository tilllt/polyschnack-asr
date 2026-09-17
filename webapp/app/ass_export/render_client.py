"""Client für den optionalen Render-Dienst ``ps-render`` (Change 200).

Der Kern der Webapp läuft **ohne** diesen Dienst vollständig: jeder Aufruf hier
mündet bei fehlendem oder sterbendem Dienst in ``RenderUnavailable`` — der
Aufrufer baut daraus eine ehrliche Meldung. Keine stillen Ausnahmen, keine
erfundenen Erfolge.

Bewusst kein Retry-Schleier: ein Render dauert Minuten, ein automatischer
Wiederholungsversuch würde die Warteschlange doppelt belegen. Der Nutzer drückt
im Zweifel erneut.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

RENDER_URL = os.getenv("RENDER_URL", "http://ps-render:8090").rstrip("/")

#: Health-Antwort kurz zwischenspeichern — der Dialog und die Preset-Liste fragen
#: häufig, der Dienst soll davon nicht geflutet werden.
HEALTH_TTL_S = float(os.getenv("RENDER_HEALTH_TTL_S", "15"))
STATUS_TIMEOUT_S = float(os.getenv("RENDER_STATUS_TIMEOUT_S", "5"))
START_TIMEOUT_S = float(os.getenv("RENDER_START_TIMEOUT_S", "120"))

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()


class RenderUnavailable(RuntimeError):
    """Dienst nicht konfiguriert, nicht erreichbar oder ohne libass/Encoder."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail or "Render-Dienst nicht verfügbar")


class RenderError(RuntimeError):
    """Der Dienst hat die Anfrage abgelehnt oder ist am Auftrag gescheitert."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _cache_get(key: str, ttl: float) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _cache_put(key: str, value: Dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), value)


def reset_cache() -> None:
    """Cache leeren (nach Job-Start oder in Tests)."""
    with _cache_lock:
        _cache.clear()


def health(ttl: Optional[float] = None) -> Dict[str, Any]:
    """``/health`` des Dienstes, kurz gecacht. Fehler werden zu einem Zustand."""
    cached = _cache_get("health", HEALTH_TTL_S if ttl is None else ttl)
    if cached is not None:
        return cached
    try:
        res = httpx.get(f"{RENDER_URL}/health", timeout=STATUS_TIMEOUT_S)
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, dict):  # pragma: no cover — Dienst ist unserer
            raise ValueError("unerwartete Health-Antwort")
    except Exception as exc:  # noqa: BLE001 — jeder Fehler heißt hier "nicht da"
        data = {
            "status": "unavailable",
            "formats": [],
            "detail": f"{type(exc).__name__}: {exc}",
        }
    _cache_put("health", data)
    return data


def available() -> bool:
    """Läuft der Dienst und kann er mindestens ein Format?"""
    return bool(formats())


def formats() -> List[Dict[str, Any]]:
    """Angebotene Formate (Capabilities des Dienstes, nichts geraten)."""
    return list(health().get("formats") or [])


def start(
    *,
    ass_bytes: bytes,
    filename: str,
    fmt: str,
    duration_s: float,
    width: int,
    height: int,
    fps: int,
    background: str,
    crf: int = 28,
    media: Optional[Tuple[str, bytes, str]] = None,
) -> Dict[str, Any]:
    """Render-Job anlegen. ``media`` = (Name, Bytes, MIME) für ``burn_mp4``."""
    files: Dict[str, Any] = {"ass": (filename, ass_bytes, "text/plain")}
    if media is not None:
        files["media"] = media
    data = {
        "format": fmt,
        "width": str(width),
        "height": str(height),
        "fps": str(fps),
        "duration_s": f"{duration_s:.3f}",
        "background": background,
        "crf": str(crf),
    }
    try:
        res = httpx.post(f"{RENDER_URL}/render", files=files, data=data,
                         timeout=START_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        raise RenderUnavailable(f"Render-Dienst nicht erreichbar: {exc}") from exc
    if res.status_code >= 400:
        code, detail = "render_rejected", res.text[:300]
        try:
            payload = res.json().get("detail")
            if isinstance(payload, dict):
                code = payload.get("error", code)
                detail = payload.get("detail", detail)
        except Exception:  # noqa: BLE001 — Klartext genügt
            pass
        raise RenderError(code, detail)
    reset_cache()          # der Dienst ist jetzt beschäftigt → Health neu holen
    return res.json()


def status(job_id: str) -> Dict[str, Any]:
    try:
        res = httpx.get(f"{RENDER_URL}/jobs/{job_id}", timeout=STATUS_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        raise RenderUnavailable(f"Render-Dienst nicht erreichbar: {exc}") from exc
    if res.status_code == 404:
        raise RenderError("unknown_job",
                          "Auftrag kennt der Render-Dienst nicht mehr (Neustart?).")
    if res.status_code >= 400:
        raise RenderError("render_error", res.text[:300])
    return res.json()


def cancel(job_id: str) -> Dict[str, Any]:
    try:
        res = httpx.delete(f"{RENDER_URL}/jobs/{job_id}", timeout=STATUS_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        raise RenderUnavailable(f"Render-Dienst nicht erreichbar: {exc}") from exc
    if res.status_code >= 400:
        raise RenderError("render_error", res.text[:300])
    reset_cache()
    return res.json()


def open_file(job_id: str) -> Tuple[httpx.Client, httpx.Response]:
    """Fertige Datei zum Streamen öffnen (ProRes wird schnell zweistellig GB).

    Rückgabe ist (Client, Antwort) — der Aufrufer **muss** beide schließen; das
    geschieht im Router im ``finally`` des Streaming-Generators. Kein
    Contextmanager, weil der Stream den Request überleben muss.
    """
    client = httpx.Client(timeout=None)
    try:
        request = client.build_request("GET", f"{RENDER_URL}/jobs/{job_id}/file")
        res = client.send(request, stream=True)
    except Exception as exc:  # noqa: BLE001
        client.close()
        raise RenderUnavailable(f"Render-Dienst nicht erreichbar: {exc}") from exc
    if res.status_code >= 400:
        detail = res.text[:300]
        res.close()
        client.close()
        if res.status_code == 409:
            raise RenderError("not_finished", "Der Auftrag läuft noch.")
        if res.status_code == 410:
            raise RenderError("expired", "Die Datei wurde bereits aufgeräumt (24 h).")
        if res.status_code == 404:
            raise RenderError("unknown_job", "Auftrag unbekannt.")
        raise RenderError("render_error", detail)
    return client, res


def filename_from_headers(res: httpx.Response, fallback: str) -> str:
    """Dateinamen aus ``Content-Disposition`` lesen (nur der Name, kein Pfad)."""
    raw = res.headers.get("content-disposition", "")
    marker = 'filename="'
    if marker in raw:
        name = raw.split(marker, 1)[1].split('"', 1)[0]
        name = os.path.basename(name).strip() or fallback
        return name
    return fallback
