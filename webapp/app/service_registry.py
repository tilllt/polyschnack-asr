"""Central registry of all ASR endpoints — geladen aus backends.yaml.

Single source of truth for:
- resource requirements (``requires``: vram/ram/disk) used by the admin
  pre-start resource check,
- endpoint capacity (``concurrency``) from which the transcribe queue derives
  the overall concurrency (Decision 3),
- feature capabilities used for the model matrix (README + GUI),
- adapter wiring (``adapter``: Modul:Klassenname) for get_client().

Weg 1 (hybrid): Jeder lokale Service hat genau EIN Image, das auf GPU UND
CPU läuft (CUDA/ggml-Binary mit CPU-Fallback via ggml_backend_init_best).
Es gibt keine CPU-Varianten mehr — die Admin-API nutzt immer ``container_name``.

Die Definitionen liegen NICHT im Code, sondern in ``backends.yaml`` (neben
diesem Modul). Neues Backend = neuer YAML-Block + Adapter-Klasse; keine
Code-Änderung an der Verdrahtung. ``available_services()`` returns services
with ``status == "active"`` (runtime up/down state comes from the Docker proxy).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_BACKENDS_FILE = Path(__file__).parent / "backends.yaml"


def _load() -> List[Dict[str, Any]]:
    with open(_BACKENDS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return list(data["services"])


SERVICES: List[Dict[str, Any]] = _load()

_VALID_PROFILES = {"default", "cpp", "qwen3", "ark", "voxtral", "moonshine", "canary"}


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
        assert s.get("container_name"), f"{s['name']} braucht container_name"
        assert isinstance(s.get("cost_per_minute_eur", 0), (int, float)) and s.get("cost_per_minute_eur", 0) >= 0
        assert isinstance(s["concurrency"], int) and s["concurrency"] >= 1
        assert s["requires"]["vram_gb"] >= 0 and s["requires"]["ram_gb"] >= 0 and s["requires"]["disk_gb"] >= 0
        assert s["compose_profile"] in _VALID_PROFILES or s["type"] == "remote"
        assert s.get("adapter") and ":" in s["adapter"], f"{s['name']} braucht 'adapter: Modul:Klasse'"
        for k, v in s["capabilities"].items():
            assert isinstance(v, (bool, str, list)), f"{s['name']}.capabilities.{k}"
    assert len({s["name"] for s in SERVICES}) == len(SERVICES), "duplicate service names"
    # container_name müssen eindeutig sein (compose-Namen kollidieren sonst)
    names = [s["container_name"] for s in SERVICES if s.get("container_name")]
    assert len(names) == len(set(names)), "container_name doppelt vergeben"
    print(f"service_registry self-check OK: {len(SERVICES)} services, total_concurrency={total_concurrency()}")
