"""APIRouter for /api/models — check model availability + trigger downloads."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..asr_client import get_client
from ..config import settings

_MODEL_CACHE = settings.DATA_DIR / "models"
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_MODEL_CACHE))
os.environ.setdefault("HF_HUB_CACHE", str(_MODEL_CACHE))

router = APIRouter(prefix="/api/models")

# Track download state (in-memory, simple)
_downloading: Dict[str, bool] = {}
_download_progress: Dict[str, str] = {}


def _check_vad() -> bool:
    """Check if Silero VAD model is importable (lazy)."""
    try:
        from silero_vad import load_silero_vad  # noqa: F401
        return True
    except Exception:
        return False


def _pyannote_importable() -> bool:
    """True wenn pyannote.audio installiert ist (Import-Check).

    Seit Option B (Diarization via CrispASR-diar-Service) ist pyannote
    NICHT mehr in der Webapp installiert — dieser Check bleibt als
    konservativer Fallback für ältere Images (False → diar-Service-Check).
    """
    try:
        import pyannote.audio  # noqa: F401
        return True
    except Exception:
        return False


def _diar_service_reachable() -> bool:
    """True wenn der diar-Service (CrispASR) per HTTP erreichbar ist."""
    try:
        resp = httpx.get(f"{settings.DIAR_URL.rstrip('/')}/health", timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def _check_diarize() -> bool:
    """Check if the diar-Service is reachable (CrispASR-Server, Option B)."""
    if _pyannote_importable():
        # Altes Image (pyannote lokal) — dort war der Import der Check.
        return True
    return _diar_service_reachable()


def _diarize_diagnosis() -> Dict[str, Any]:
    """Detaillierte Diagnose, warum die Diarization (nicht) verfügbar ist.

    Rückgabe: {available, code, message, service, components}
      codes: ok | diar-unreachable | diar-error
    Seit Option B läuft die Diarization im CrispASR-diar-Container —
    kein HF_TOKEN, kein pyannote-Download mehr in der Webapp.
    """
    url = settings.DIAR_URL.rstrip("/")
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        resp.raise_for_status()
        return {"available": True, "code": "ok", "service": url,
                "message": "Diar-Service erreichbar (CrispASR).",
                "components": [{"repo": "diar-service", "status": 200,
                                "code": "ok", "message": "health ok"}]}
    except httpx.HTTPStatusError as exc:
        return {"available": False, "code": "diar-error", "service": url,
                "message": f"Diar-Service antwortete mit HTTP "
                           f"{exc.response.status_code}.",
                "components": []}
    except Exception as exc:
        return {"available": False, "code": "diar-unreachable", "service": url,
                "message": f"Diar-Service nicht erreichbar: {exc}",
                "components": []}


def _download_vad():
    """Download Silero VAD model (ONNX, lightweight)."""
    if _downloading.get("vad"):
        return
    _downloading["vad"] = True
    _download_progress["vad"] = "starting"
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "silero-vad"],
            capture_output=True, check=True,
        )
        # Force model download by importing
        from silero_vad import load_silero_vad  # noqa: F811
        load_silero_vad(onnx=True)
        _download_progress["vad"] = "done"
    except Exception as exc:
        _download_progress["vad"] = f"failed: {exc}"
    finally:
        _downloading["vad"] = False


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/status")
def model_status() -> Dict[str, Any]:
    """Return availability of VAD, diarization models, HF_TOKEN, and ASR device."""
    asr_device = "unknown"
    try:
        resp = httpx.get(f"{settings.ASR_URL}/health", timeout=3)
        resp.raise_for_status()
        info = resp.json()
        asr_device = info.get("device", "unknown")
    except Exception:
        asr_device = "unreachable"

    client = get_client()

    # Detaillierte Diagnose: warum lädt Diarization (nicht)?
    diag = _diarize_diagnosis()
    vad_available = _check_vad()
    vad_diag = {
        "available": vad_available,
        "code": "ok" if vad_available else "vad-missing",
        "message": "" if vad_available else (
            "silero_vad ist nicht installiert — "
            "Container-Image prüfen / neu bauen."
        ),
    }

    return {
        "vad_available": vad_available,
        "diarize_available": diag["available"],
        "diar_service": diag["service"],
        "asr_device": asr_device,
        "backend": client.capabilities.label,
        "features": {
            "streaming": client.capabilities.streaming,
            "noise_reduce": client.capabilities.noise_reduce,
            "async_jobs": client.capabilities.async_jobs,
        },
        "downloading": _downloading,
        "download_progress": _download_progress,
        # Diagnose-Felder: präzise Fehlerursache statt nur bool
        "vad_diag": vad_diag,
        "diarize_diag": diag,
    }


class DownloadResponse(BaseModel):
    status: str
    message: str


@router.post("/vad/download")
def download_vad() -> DownloadResponse:
    if _check_vad():
        return DownloadResponse(status="ok", message="already installed")
    if _downloading.get("vad"):
        return DownloadResponse(status="running", message="already downloading")
    thread = threading.Thread(target=_download_vad, daemon=True)
    thread.start()
    return DownloadResponse(status="started", message="VAD model download started")


@router.post("/diarize/download")
def download_diarize() -> DownloadResponse:
    """Kein Download mehr nötig — Diarization läuft im CrispASR-diar-Container.

    Seit Option B liegt das Diarization-Modell (parakeet-GGUF) als Volume
    im diar-Service (./DATA/diar-models/). Der Endpoint bleibt als
    Kompatibilitäts-Stub für ältere Frontends und meldet den neuen Zustand.
    """
    if _check_diarize():
        return DownloadResponse(
            status="ok",
            message="Diarization verfügbar (CrispASR-diar-Service).",
        )
    return DownloadResponse(
        status="service-unreachable",
        message="Diar-Service nicht erreichbar — Container 'diar' prüfen "
                "(Modell liegt unter ./DATA/diar-models/).",
    )
