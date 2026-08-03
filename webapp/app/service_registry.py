"""Central registry of all ASR endpoints (Task 2).

Single source of truth for:
- resource requirements (``requires``: vram/ram/disk) used by the admin
  pre-start resource check,
- endpoint capacity (``concurrency``) from which the transcribe queue derives
  the overall concurrency (Decision 3),
- feature capabilities used for the model matrix (README + GUI).

GPU/CPU-Automatik (Option B2): Jeder lokale Service kann eine CPU-Variante
haben (``cpu_container_name``). Die Admin-API startet automatisch die
GPU- oder CPU-Variante, je nachdem ob der Host NVIDIA-Container-Toolkit
hat (``host_info()['has_nvidia']``) — kein manueller Wechsel mehr.

Kept deliberately small: a plain dict + assert self-check. No image/container
duplicates — that is compose's job. ``available_services()`` returns services
with ``status == \"active\"`` (runtime up/down state comes from the Docker proxy).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SERVICES: List[Dict[str, Any]] = [
    {
        "name": "pk-python",
        "backend": "pk-python",
        "compose_profile": "default",
        "container_name": "polyschnack-asr",
        "type": "local",
        "cost_per_minute_eur": 0.0,
        "concurrency": 1,
        "model": "parakeet-tdt-0.6b-v3-onnx",
        "health_url": "",  # "" -> settings.ASR_URL; only our own servers report VRAM
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
        "container_name": "polyschnack-cpp",
        "cpu_container_name": "polyschnack-cpp-cpu",
        "type": "local",
        "cost_per_minute_eur": 0.0,
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
            "device": ["gpu", "cpu"],
        },
        "status": "active",
    },
    {
        "name": "qwen3-asr",
        "backend": "qwen3-asr",
        "compose_profile": "qwen3",
        "container_name": "qwen3-asr",
        "cpu_container_name": "qwen3-asr-cpu",
        "type": "local",
        "cost_per_minute_eur": 0.0,
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
            "device": ["gpu", "cpu"],
        },
        "status": "active",
    },
    {
        "name": "ark-asr",
        "backend": "ark-asr",
        "compose_profile": "ark",
        "container_name": "ark-asr",
        "cpu_container_name": "ark-asr-cpu",
        "type": "local",
        "cost_per_minute_eur": 0.0,
        "concurrency": 1,
        "model": "ark-asr-3b-q8_0.gguf",
        "requires": {"vram_gb": 5, "ram_gb": 6, "disk_gb": 4},
        "capabilities": {
            "word_timestamps": True,  # CrispASR verbose_json liefert word-level
            "streaming": False,
            "async_jobs": False,
            "noise_reduce": False,
            "vad": "external",
            "diarization": "external",
            "enhance": True,
            "languages": ["de", "en"],
            "device": ["gpu", "cpu"],
        },
        "status": "active",
    },
    {
        "name": "voxtral",
        "backend": "voxtral",
        "compose_profile": "voxtral",
        "container_name": "polyschnack-voxtral",
        "type": "local",
        "cost_per_minute_eur": 0.0,
        "concurrency": 1,
        "model": "Voxtral-Mini-4B-Realtime-2602 (Q4_K_M)",
        "url": "http://polyschnack-voxtral:8000",  # voxtral.cpp / vLLM-compatible server
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


def resolve_container(svc: Dict[str, Any], has_nvidia: bool) -> str:
    """Container-Name für einen Service — GPU/CPU-Variante automatisch wählen.

    Wenn der Host kein NVIDIA-Container-Toolkit hat (``has_nvidia=False``)
    und der Service eine CPU-Variante besitzt (``cpu_container_name``),
    wird diese gewählt. Sonst der GPU-Container (``container_name``).
    """
    if not has_nvidia and svc.get("cpu_container_name"):
        return svc["cpu_container_name"]
    return svc["container_name"]


def total_concurrency() -> int:
    """Sum of endpoint capacities — the derived transcribe concurrency (Decision 3)."""
    return sum(s["concurrency"] for s in available_services())


if __name__ == "__main__":
    # Self-check: registry stays valid. Run with `python -m app.service_registry`.
    for s in SERVICES:
        assert s["name"] and s["backend"] and s["compose_profile"]
        assert s["type"] in {"local", "remote"}
        assert s.get("container_name"), f"{s['name']} braucht container_name"
        assert isinstance(s.get("cost_per_minute_eur", 0), (int, float)) and s.get("cost_per_minute_eur", 0) >= 0
        assert isinstance(s["concurrency"], int) and s["concurrency"] >= 1
        assert s["requires"]["vram_gb"] >= 0 and s["requires"]["ram_gb"] >= 0 and s["requires"]["disk_gb"] >= 0
        assert s["compose_profile"] in _VALID_PROFILES or s["type"] == "remote"
        for k, v in s["capabilities"].items():
            assert isinstance(v, (bool, str, list)), f"{s['name']}.capabilities.{k}"
    assert len({s["name"] for s in SERVICES}) == len(SERVICES), "duplicate service names"
    # CPU-Varianten-Referenzen prüfen (jeweils eigener Container-Name)
    names = {s["container_name"] for s in SERVICES}
    for s in SERVICES:
        if s.get("cpu_container_name"):
            assert s["cpu_container_name"] not in names, f"CPU-Name kollidiert: {s['cpu_container_name']}"
    print(f"service_registry self-check OK: {len(SERVICES)} services, total_concurrency={total_concurrency()}")
