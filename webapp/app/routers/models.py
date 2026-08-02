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
    """True wenn pyannote.audio installiert ist (Import-Check)."""
    try:
        import pyannote.audio  # noqa: F401
        return True
    except Exception:
        return False


def _check_diarize() -> bool:
    """Check if pyannote pipeline can load (model cached)."""
    return _pyannote_importable()


def _hf_token() -> bool:
    return bool(os.getenv("HF_TOKEN"))


# Komponenten der pyannote speaker-diarization-3.1 Pipeline (config.yaml):
#   embedding:    pyannote/wespeaker-voxceleb-resnet34-LM
#   segmentation: pyannote/segmentation-3.0
# plus das PLDA/community-Modell, das die Pipeline intern nachlädt.
DIARIZE_REPOS = [
    "pyannote/speaker-diarization-3.1",
    "pyannote/segmentation-3.0",
    "pyannote/wespeaker-voxceleb-resnet34-LM",
    "pyannote/speaker-diarization-community-1",
]


def _probe_repo(repo_id: str, token: str | None) -> Dict[str, Any]:
    """Prüft Erreichbarkeit eines HF-Repos per API-Call (schnell, kein Download).

    HTTP-Status → Ursache:
      200 → ok
      401 → Token fehlt/ungültig (kein Login)
      403 → gated (Nutzungsbedingungen nicht akzeptiert)
      404 → Repo existiert nicht
      sonst / Exception → network-error
    """
    if not token:
        return {"status": None, "code": "no-token", "repo": repo_id,
                "message": "HF_TOKEN nicht gesetzt — Modell kann nicht authentifiziert geladen werden."}
    enc = repo_id.replace("/", "%2F")
    url = f"https://huggingface.co/api/models/{enc}"
    try:
        resp = httpx.get(url, timeout=15, headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:
        return {"status": None, "code": "network-error", "repo": repo_id,
                "message": f"HuggingFace nicht erreichbar: {exc.__class__.__name__}: {exc}"}
    code = resp.status_code
    if code == 200:
        return {"status": 200, "code": "ok", "repo": repo_id, "message": ""}
    if code == 401:
        return {"status": 401, "code": "unauthorized", "repo": repo_id,
                "message": f"Token ungültig oder kein Login (HTTP 401) für {repo_id}."}
    if code == 403:
        return {"status": 403, "code": "gated", "repo": repo_id,
                "message": f"{repo_id} ist gated — Nutzungsbedingungen auf "
                           f"huggingface.co/{repo_id} akzeptieren (Agree and access repository)."}
    if code == 404:
        return {"status": 404, "code": "not-found", "repo": repo_id,
                "message": f"Repo {repo_id} existiert nicht (HTTP 404) — "
                           "Modell-ID in der Pipeline-Konfiguration prüfen."}
    return {"status": code, "code": "http-error", "repo": repo_id,
            "message": f"Unerwarteter HTTP-Status {code} für {repo_id}."}


def _diarize_diagnosis() -> Dict[str, Any]:
    """Detaillierte Diagnose, warum die Diarization-Pipeline (nicht) lädt.

    Rückgabe: {available, code, message, repo, components}
      codes: ok | no-token | pyannote-missing | gated | not-found |
             unauthorized | network-error | http-error
    """
    if not _hf_token():
        return {"available": False, "code": "no-token", "repo": None,
                "message": "HF_TOKEN nicht gesetzt (compose.yml environment). "
                           "Diarization ist ohne Token nicht nutzbar.",
                "components": []}
    if not _pyannote_importable():
        return {"available": False, "code": "pyannote-missing", "repo": None,
                "message": "pyannote.audio ist nicht installiert — "
                           "Container-Image prüfen / neu bauen.",
                "components": []}

    token = os.getenv("HF_TOKEN")
    components: list[Dict[str, Any]] = []
    first_fail: Dict[str, Any] | None = None
    for repo in DIARIZE_REPOS:
        probe = _probe_repo(repo, token)
        components.append(probe)
        if probe["code"] != "ok" and first_fail is None:
            first_fail = probe

    if first_fail is None:
        return {"available": True, "code": "ok", "repo": None,
                "message": "Alle Diarization-Komponenten erreichbar.",
                "components": components}

    return {"available": False, "code": first_fail["code"],
            "repo": first_fail["repo"],
            "message": first_fail["message"],
            "components": components}


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


def _download_diarize():
    """Download pyannote model from HuggingFace (~300MB)."""
    if _downloading.get("diarize"):
        return
    if not _hf_token():
        _download_progress["diarize"] = "no-token"
        return
    _downloading["diarize"] = True
    _download_progress["diarize"] = "starting"
    try:
        from pyannote.audio import Pipeline  # noqa: F811
        token = os.getenv("HF_TOKEN")
        Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
            cache_dir=str(_MODEL_CACHE),
        )
        _download_progress["diarize"] = "done"
    except Exception as exc:
        _download_progress["diarize"] = f"failed: {exc}"
    finally:
        _downloading["diarize"] = False


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
        "hf_token": _hf_token(),
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
    if not _hf_token():
        return DownloadResponse(
            status="no-token",
            message="HF_TOKEN not set — add it to compose.yml:\n"
                    "environment:\n"
                    "  HF_TOKEN: hf_your_token_here\n\n"
                    "Get a token at https://huggingface.co/settings/tokens",
        )
    if _check_diarize():
        return DownloadResponse(status="ok", message="already installed")
    if _downloading.get("diarize"):
        return DownloadResponse(status="running", message="already downloading")
    thread = threading.Thread(target=_download_diarize, daemon=True)
    thread.start()
    return DownloadResponse(
        status="started",
        message="pyannote model download started (~300 MB)",
    )
