"""APIRouter for /api/models — check model availability + trigger downloads."""
from __future__ import annotations

import os
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
    """Check if Silero VAD is available (onnxruntime-Session, Change 060)."""
    from app import vad as vad_mod

    return vad_mod.vad_available()


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
        features = {}
        try:
            features = resp.json() or {}
        except Exception:
            features = {}
        return {"available": True, "code": "ok", "service": url,
                "message": "Diar-Service erreichbar (CrispASR).",
                "features": features,
                "components": [{"repo": "diar-service", "status": 200,
                                "code": "ok", "message": "health ok"}]}
    except httpx.HTTPStatusError as exc:
        return {"available": False, "code": "diar-error", "service": url,
                "message": f"Diar-Service antwortete mit HTTP "
                           f"{exc.response.status_code}.",
                "features": {}, "components": []}
    except Exception as exc:
        return {"available": False, "code": "diar-unreachable", "service": url,
                "message": f"Diar-Service nicht erreichbar: {exc}",
                "features": {}, "components": []}


def _aligner_diagnosis() -> Dict[str, Any]:
    """Diagnose des Forced-Aligner-Service (crispr-align).

    Rückgabe: {available, code, message, service, features, components}
      codes: ok | aligner-error | aligner-unreachable | aligner-disabled
    Der Aligner ist OPTIONAL: POLYSCHNACK_ALIGN_WORDS=false deaktiviert die
    Karaoke-Wort-Synchronisation bewusst. Der Health-Endpoint des Service
    ist self-describing (Modell, max_duration_s, word_timestamps, device) —
    genau das liest die Webapp hier aus.
    """
    from ..aligner_client import ALIGN_WORDS_ENABLED

    if not ALIGN_WORDS_ENABLED:
        return {"available": False, "code": "aligner-disabled",
                "service": None, "message": "Forced-Alignment deaktiviert "
                "(POLYSCHNACK_ALIGN_WORDS=false).",
                "features": {}, "components": []}
    url = os.getenv("CRISP_ALIGN_URL", "http://crispr-align:5099").rstrip("/")
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        resp.raise_for_status()
        features = {}
        try:
            features = resp.json() or {}
        except Exception:
            features = {}
        # Feature-Matrix-Basis: was der Aligner KANN (aus Health + Code).
        features.setdefault("service", "aligner")
        features.setdefault("word_timestamps", True)
        features.setdefault("max_duration_s", 400.0)
        return {"available": True, "code": "ok", "service": url,
                "message": "Aligner-Service erreichbar (qwen3-forced-aligner).",
                "features": features,
                "components": [{"repo": "aligner-service", "status": 200,
                                "code": "ok", "message": "health ok"}]}
    except httpx.HTTPStatusError as exc:
        return {"available": False, "code": "aligner-error", "service": url,
                "message": f"Aligner-Service antwortete mit HTTP "
                           f"{exc.response.status_code}.",
                "features": {}, "components": []}
    except Exception as exc:
        return {"available": False, "code": "aligner-unreachable",
                "service": url,
                "message": f"Aligner-Service nicht erreichbar: {exc} — "
                           f"Karaoke-Wort-Highlight fällt auf Backend-"
                           f"Timestamps zurück.",
                "features": {}, "components": []}


def _download_vad():
    """Download Silero VAD model (ONNX, ~2 MB) — Change 060 (kein pip mehr)."""
    if _downloading.get("vad"):
        return
    _downloading["vad"] = True
    _download_progress["vad"] = "starting"
    try:
        from app import vad as vad_mod

        path = vad_mod._ensure_model()
        _download_progress["vad"] = "done" if path else "failed: download failed"
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
    align_diag = _aligner_diagnosis()
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
        "align_available": align_diag["available"],
        "align_service": align_diag["service"],
        "asr_device": asr_device,
        "backend": client.capabilities.label,
        "features": {
            "streaming": client.capabilities.streaming,
            "noise_reduce": client.capabilities.noise_reduce,
            "async_jobs": client.capabilities.async_jobs,
            "word_timestamps": client.capabilities.word_timestamps,
            "native_punctuation": client.capabilities.native_punctuation,
            "languages": client.capabilities.languages,
            "accepts_compressed": client.capabilities.accepts_compressed,
        },
        "downloading": _downloading,
        "download_progress": _download_progress,
        # Diagnose-Felder: präzise Fehlerursache statt nur bool
        "vad_diag": vad_diag,
        "diarize_diag": diag,
        "aligner_diag": align_diag,
    }


@router.get("/services")
def services_status() -> Dict[str, Any]:
    """Service-Matrix: welche Sidecar-Services laufen und welche Features
    sie anbieten.

    Liefert für jeden Service {available, code, service, features} — Basis
    für die Feature-Matrix (Frontend) und Debugging („läuft der Aligner?").
    Enthält bewusst KEINE Secrets, nur Health + self-describing Features.
    """
    client = get_client()
    return {
        "asr": {
            "available": asr_device_ok(),
            "service": settings.ASR_URL,
            "features": {
                "backend": client.capabilities.label,
                "device": asr_device_name(),
                "streaming": client.capabilities.streaming,
                "noise_reduce": client.capabilities.noise_reduce,
                "async_jobs": client.capabilities.async_jobs,
                "word_timestamps": client.capabilities.word_timestamps,
                "native_punctuation": client.capabilities.native_punctuation,
                "languages": client.capabilities.languages,
                "accepts_compressed": client.capabilities.accepts_compressed,
            },
        },
        "vad": {
            "available": _check_vad(),
            "service": "local (silero_vad)",
            "features": {"onnx": True},
        },
        "diar": _diarize_diagnosis(),
        "aligner": _aligner_diagnosis(),
    }


def asr_device_ok() -> bool:
    try:
        resp = httpx.get(f"{settings.ASR_URL}/health", timeout=3)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def asr_device_name() -> str:
    try:
        resp = httpx.get(f"{settings.ASR_URL}/health", timeout=3)
        resp.raise_for_status()
        return str(resp.json().get("device", "unknown"))
    except Exception:
        return "unreachable"


class DownloadResponse(BaseModel):
    status: str
    message: str


@router.post("/vad/download")
def download_vad() -> DownloadResponse:
    if _check_vad():
        return DownloadResponse(status="ok", message="already installed")
    if _downloading.get("vad"):
        return DownloadResponse(status="running", message="already downloading")
    _downloading["vad"] = True
    # Change 155 (Schritt 6): statt nacktem Thread als Queue-Job
    # (eigener "ops"-Slot; Key dedupliziert — nur ein Download gleichzeitig).
    from ..queue import QueueError, queue_manager

    try:
        # rec_id=0: Sentinel — der vad-Job ist keinem Recording zugeordnet
        # (Key "vad-download" dedupliziert, rec_id wird nicht genutzt).
        queue_manager.enqueue(0, user_id=None, backend="ops", kind="vad",
                              key="vad-download")
        return DownloadResponse(status="started", message="VAD model download started")
    except QueueError:
        _downloading.pop("vad", None)
        return DownloadResponse(status="running", message="already downloading")


def run_vad_download_job() -> None:
    """Change 155 (Schritt 6): Queue-Dispatch-Ziel für VAD-Downloads."""
    try:
        _download_vad()
    finally:
        _downloading.pop("vad", None)


@router.post("/diarize/download")
def download_diarize() -> DownloadResponse:
    """Kein Download mehr nötig — Diarization läuft im CrispASR-diar-Container.

    Seit Option B liegt das Diarization-Modell (parakeet-GGUF) als Volume
    im diar-Service (./DATA/models/). Der Endpoint bleibt als
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
                "(Modell liegt unter ./DATA/models/).",
    )
