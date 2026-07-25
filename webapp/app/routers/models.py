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


def _check_diarize() -> bool:
    """Check if pyannote pipeline can load (model cached)."""
    try:
        import pyannote.audio  # noqa: F401
        return True
    except Exception:
        return False


def _hf_token() -> bool:
    return bool(os.getenv("HF_TOKEN"))


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
            use_auth_token=token,
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

    return {
        "vad_available": _check_vad(),
        "diarize_available": _check_diarize(),
        "hf_token": _hf_token(),
        "asr_device": asr_device,
        "downloading": _downloading,
        "download_progress": _download_progress,
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
