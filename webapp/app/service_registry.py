"""Central registry of all ASR endpoints (Task 2).

Single source of truth for:
- resource requirements (``requires``: vram/ram/disk) used by the admin
  pre-start resource check,
- endpoint capacity (``concurrency``) from which the transcribe queue derives
  the overall concurrency (Decision 3),
- feature capabilities used for the model matrix (README + GUI).

Kept deliberately small: a plain dict + assert self-check. No image/container
duplicates — that is compose's job. ``available_services()`` returns services
with ``status == "active"`` (runtime up/down state comes from the Docker proxy).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SERVICES: List[Dict[str, Any]] = [
    {
        "name": "pk-python",
        "backend": "pk-python",
        "compose_profile": "default",
        "type": "local",
        "concurrency": 1,
        "model": "parakeet-tdt-0.6b-v3-onnx",
        "requires": {"vram_gb": 6, "ram_gb": 8, "disk_gb": 5},
        "capabilities": {
            "word_timestamps": True,
            "streaming": True,
            "async_jobs": True,
            "noise_reduce": True,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu", "cpu"],
        },
        "status": "active",
    },
    {
        "name": "pk-cpp",
        "backend": "pk-cpp",
        "compose_profile": "cpp",
        "type": "local",
        "concurrency": 1,
        "model": "parakeet-tdt-0.6b-v3-q8_0.gguf",
        "requires": {"vram_gb": 2, "ram_gb": 4, "disk_gb": 2},
        "capabilities": {
            "word_timestamps": True,  # same model as pk-python, timestamps model-inherent
            "streaming": False,
            "async_jobs": False,
            "noise_reduce": False,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu"],
        },
        "status": "active",
    },
    {
        "name": "qwen3-asr",
        "backend": "qwen3-asr",
        "compose_profile": "qwen3",
        "type": "local",
        "concurrency": 1,
        "model": "qwen3-asr-0.6b-q8_0.gguf + forced-aligner",
        "requires": {"vram_gb": 3, "ram_gb": 6, "disk_gb": 4},
        "capabilities": {
            "word_timestamps": True,  # via forced aligner
            "streaming": False,
            "async_jobs": False,
            "noise_reduce": False,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu"],
        },
        "status": "active",
    },
    {
        "name": "ark-asr",
        "backend": "ark-asr",
        "compose_profile": "ark",
        "type": "local",
        "concurrency": 1,
        "model": "ark-asr-3b-q8_0.gguf",
        "requires": {"vram_gb": 5, "ram_gb": 6, "disk_gb": 4},
        "capabilities": {
            "word_timestamps": "verify",  # checked against real API response in Task 3
            "streaming": False,
            "async_jobs": False,
            "noise_reduce": False,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu"],
        },
        "status": "active",
    },
    {
        "name": "voxtral",
        "backend": "voxtral",
        "compose_profile": "voxtral",
        "type": "local",
        "concurrency": 1,
        "model": "Voxtral-Mini-4B-Realtime-2602 (Q4_K_M)",
        "requires": {"vram_gb": 5, "ram_gb": 6, "disk_gb": 4},
        "capabilities": {
            "word_timestamps": "verify",  # Mistral: not trained for timestamps (likely False)
            "streaming": True,  # realtime model emits one token per 80ms frame
            "async_jobs": False,
            "noise_reduce": False,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu"],
        },
        "status": "active",
    },
]

_VALID_PROFILES = {"default", "cpp", "qwen3", "ark", "voxtral"}


def get_service(name: str) -> Optional[Dict[str, Any]]:
    """Return the service dict for *name* (by ``name`` or ``backend``), or None."""
    for s in SERVICES:
        if s["name"] == name or s["backend"] == name:
            return s
    return None


def list_services() -> List[Dict[str, Any]]:
    return list(SERVICES)


def available_services() -> List[Dict[str, Any]]:
    """Services that can accept jobs (status active). Runtime state is separate."""
    return [s for s in SERVICES if s["status"] == "active"]


def total_concurrency() -> int:
    """Sum of endpoint capacities — the derived transcribe concurrency (Decision 3)."""
    return sum(s["concurrency"] for s in available_services())


if __name__ == "__main__":
    # Self-check: registry stays valid. Run with `python -m app.service_registry`.
    for s in SERVICES:
        assert s["name"] and s["backend"] and s["compose_profile"]
        assert s["type"] in {"local", "remote"}
        assert isinstance(s["concurrency"], int) and s["concurrency"] >= 1
        assert s["requires"]["vram_gb"] >= 0 and s["requires"]["ram_gb"] >= 0 and s["requires"]["disk_gb"] >= 0
        assert s["compose_profile"] in _VALID_PROFILES or s["type"] == "remote"
        for k, v in s["capabilities"].items():
            assert isinstance(v, (bool, str, list)), f"{s['name']}.capabilities.{k}"
    assert len({s["name"] for s in SERVICES}) == len(SERVICES), "duplicate service names"
    print(f"service_registry self-check OK: {len(SERVICES)} services, total_concurrency={total_concurrency()}")
