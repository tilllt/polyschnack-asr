"""dispatcher/backends/base.py — InferenceBackend-Protokoll (Change 020).

Provider-Abstraktion über GPU-Instanz-Anbieter. Implementierungen:

- Stufe 1 (günstig, verschlüsselt): local, vast, theta
- Stufe 2 (EU-only, Cloud-Act-frei): nebius, hetzner, verda, scaleway,
  ovhcloud, gcore, genesis

`jurisdiction` ("eu" | "us" | "uk") steuert Modus-Sperren: Im EU-only-Modus
(Stufe 2) werden alle Backends mit jurisdiction != "eu" abgelehnt.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GpuClass(str, Enum):
    """GPU-Klassen für das Mapping small/medium/large ↔ VRAM."""

    SMALL = "small"      # 12–16 GB (ASR-Stufe)
    MEDIUM = "medium"    # 16–24 GB (ps-post-Stufe)
    LARGE = "large"      # > 24 GB


class DataClass(str, Enum):
    """Datenklasse eines Jobs — steuert Backend-Zulässigkeit."""

    INTERNAL = "internal"
    CRITICAL = "critical"


@dataclass(frozen=True)
class GpuFilter:
    """Suchfilter für list_offers."""

    gpu_class: GpuClass = GpuClass.SMALL
    min_vram_gb: int = 0
    region: str | None = None        # z. B. "EU", "DE", "FI"
    max_price_usd_h: float | None = None
    count: int = 1


@dataclass(frozen=True)
class Offer:
    """Ein mietbares Angebot."""

    provider: str
    offer_id: str
    gpu_name: str
    vram_gb: int
    price_usd_h: float
    region: str
    reliability: float | None = None


@dataclass
class Endpoint:
    """Erreichbarer Job-Endpoint einer Instanz."""

    url: str
    token: str = ""


@dataclass
class Instance:
    """Gemietete Instanz (provider-spezifische Metadaten in `meta`)."""

    provider: str
    instance_id: str
    offer_id: str = ""
    region: str = ""
    status: str = "creating"          # creating | running | error
    endpoint: Endpoint | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobResult:
    """Ergebnis eines poll()-Aufrufs."""

    status: str                       # queued | running | done | failed
    job_id: str = ""
    progress: float | None = None     # 0..1
    result_url: str | None = None
    error: str | None = None


class InferenceBackend(abc.ABC):
    """Interface für GPU-Instanz-Backends."""

    provider_name: str = "?"
    jurisdiction: str = "unknown"     # "eu" | "us" | "uk"

    @abc.abstractmethod
    def list_offers(self, flt: GpuFilter) -> list[Offer]:
        """Passende Angebote suchen (Preis aufsteigend)."""

    @abc.abstractmethod
    def acquire(
        self,
        offer: Offer,
        image: str,
        disk_gb: int = 50,
        env: dict[str, str] | None = None,
    ) -> Instance:
        """Instanz für ein Angebot mieten (env = Job-Schlüssel u. a.)."""

    @abc.abstractmethod
    def wait_ready(self, instance: Instance, timeout_s: int = 900) -> Endpoint:
        """Warten bis die Instanz Jobs annimmt; liefert den Endpoint."""

    @abc.abstractmethod
    def submit_job(self, endpoint: Endpoint, job: dict[str, Any]) -> str:
        """Job einreichen; liefert die job_id."""

    @abc.abstractmethod
    def poll(self, instance: Instance, job_id: str) -> JobResult:
        """Job-Status abfragen."""

    @abc.abstractmethod
    def destroy(self, instance: Instance) -> None:
        """Instanz beenden (NIE nur stoppen — immer destroyen)."""

    def instance_meta(self, instance: Instance) -> dict[str, Any]:
        """Audit-Metadaten (Provider, Region, Kosten-Schätzung)."""
        return {
            "provider": instance.provider,
            "instance_id": instance.instance_id,
            "region": instance.region,
            "jurisdiction": self.jurisdiction,
        }


def backend_allowed(
    backend: InferenceBackend,
    data_class: DataClass,
    eu_only: bool,
) -> bool:
    """Modus-Regel (Change 020): EU-only sperrt alle Nicht-EU-Backends."""
    if eu_only and data_class == DataClass.CRITICAL:
        return backend.jurisdiction == "eu"
    if eu_only:
        return backend.jurisdiction == "eu"
    # Stufe 1: alle Backends erlaubt; critical erzwingt auch hier EU:
    return not (data_class == DataClass.CRITICAL and backend.jurisdiction != "eu")
