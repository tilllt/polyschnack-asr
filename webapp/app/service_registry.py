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
Es gibt keine CPU-Varianten mehr — die Admin-API nutzt immer ``name``.

Option C: Service-Name = Profil = Container = Backend-ID. ``container_name``
wird von Docker-Compose automatisch vom Service-Namen übernommen, die URL
wird aus ``name`` + ``port`` abgeleitet (http://<name>:<port>), die
URL-Env-Variable automatisch aus der ID (``<ID>_URL``, z. B.
``CRISPR_QWEN3_URL``). Damit gibt es genau EINEN Namen pro Backend über alle
Ebenen hinweg — kein manuelles Mapping nötig.

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
# VAD-Modelle für den Container-Benchmark (Change 062) — siehe vad_models.yaml.
_VAD_MODELS_FILE = Path(__file__).parent / "vad_models.yaml"


def _load() -> List[Dict[str, Any]]:
    with open(_BACKENDS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return list(data["services"])


def _load_vad_models() -> Dict[str, Dict[str, Any]]:
    """VAD-Modell-Registry (Change 062): name → {engine, license, productive}."""
    with open(_VAD_MODELS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def get_vad_model(name: str) -> Optional[Dict[str, Any]]:
    """VAD-Modell per Name (None wenn unbekannt)."""
    return _load_vad_models().get(name)


# Diar-Methoden für den Container-Benchmark (Change 136) — diar_models.yaml.
_DIAR_MODELS_FILE = Path(__file__).parent / "diar_models.yaml"


def _load_diar_models() -> Dict[str, Dict[str, Any]]:
    """Diar-Methoden-Registry (Change 136): name → {method, license, productive}."""
    with open(_DIAR_MODELS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def get_diar_model(name: str) -> Optional[Dict[str, Any]]:
    """Diar-Methode per Name (None wenn unbekannt)."""
    return _load_diar_models().get(name)


SERVICES: List[Dict[str, Any]] = _load()

_VALID_PROFILES = {"default", "crispr-pk-cpp", "crispr-qwen3", "crispr-ark",
                   "crispr-moonshine-de", "crispr-canary"}


def get_service(name: str) -> Optional[Dict[str, Any]]:
    """Return the service dict for *name* (by ``name`` or ``backend``), or None."""
    for s in SERVICES:
        if s["name"] == name or s["backend"] == name:
            return s
    return None


def container_name(svc: Dict[str, Any]) -> str:
    """Docker-Container-Name = Service-Name (Option C, kein container_name-Feld)."""
    return svc["name"]


def service_url(svc: Dict[str, Any]) -> str:
    """Compose-Netzwerk-URL aus name + port (z. B. http://crispr-qwen3:5094)."""
    return f"http://{svc['name']}:{svc['port']}"


def service_url_env(svc: Dict[str, Any]) -> str:
    """URL-Env-Variable = <ID>_URL (z. B. CRISPR_QWEN3_URL), abgeleitet aus name."""
    return svc["name"].upper().replace("-", "_") + "_URL"


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
        assert isinstance(s.get("cost_per_minute_eur", 0), (int, float)) and s.get("cost_per_minute_eur", 0) >= 0
        assert isinstance(s["concurrency"], int) and s["concurrency"] >= 1
        assert s["requires"]["vram_gb"] >= 0 and s["requires"]["ram_gb"] >= 0 and s["requires"]["disk_gb"] >= 0
        assert s["compose_profile"] in _VALID_PROFILES or s["type"] == "remote"
        # Remote-Backends (OpenAI/Mistral/Groq/…) haben keinen lokalen Port
        # und keinen Container — der Check gilt nur fuer lokale Services.
        assert s["type"] == "remote" or (isinstance(s.get("port"), int) and 1 <= s["port"] <= 65535), \
            f"{s['name']} braucht gueltigen port"
        assert s.get("adapter") and ":" in s["adapter"], f"{s['name']} braucht 'adapter: Modul:Klasse'"
        for k, v in s["capabilities"].items():
            assert isinstance(v, (bool, str, list)), f"{s['name']}.capabilities.{k}"
    assert len({s["name"] for s in SERVICES}) == len(SERVICES), "duplicate service names"
    # Service-Namen = Container-Namen (Option C) — müssen eindeutig sein
    names = [s["name"] for s in SERVICES]
    assert len(names) == len(set(names)), "Service-Name doppelt vergeben"
    print(f"service_registry self-check OK: {len(SERVICES)} services, total_concurrency={total_concurrency()}")
