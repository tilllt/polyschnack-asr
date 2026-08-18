"""dispatcher/scheduler.py — Queue-Stufen-Orchestrierung (Change 020).

Der Scheduler verbindet die Webapp-Queue mit den GPU-Provider-Backends:

- **Backend-Auswahl** (`choose_backend`): `local` (die Box) wird bevorzugt —
  solange die Queue-Tiefe unter der Burst-Schwelle liegt. Steigt die Queue
  (Engpass), wird ein Stufe-1-Backend (vast/theta) gewählt. Die
  `backend_allowed()`-Regel filtert nach Datenklasse + Modus (EU-only sperrt
  Nicht-EU-Backends; `critical` erzwingt EU).
- **Job-Ausführung** (`run_job`): offer suchen → mieten (acquire) → ready
  warten → submit → poll → **Destroy im finally** (Regel: nie nur stoppen).
  Kosten werden pro Job über den CostTracker geloggt.
- **Auto-Destroy-Watchdog** (`destroy_stale`): Instanzen, deren Lebensdauer
  die TTL überschreitet (auch bei Orchestrierungsausfällen), werden direkt
  destruiert — verhindert vergessene Instanzen (betriebliche Erfahrung).

Stufe 1 = günstige On-Demand-Backends für internal-Jobs (E2E-verschlüsselt);
Stufe 2 = EU-only-Modus (Pflicht für critical, global aktivierbar).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .backends.base import (
    DataClass,
    Endpoint,
    GpuFilter,
    InferenceBackend,
    Instance,
    JobResult,
    Offer,
    backend_allowed,
)
from .costs import CostTracker, JobCost

log = logging.getLogger(__name__)


class SchedulerError(RuntimeError):
    """Basis-Fehler des Schedulers."""


class NoBackendAvailable(SchedulerError):
    """Kein Backend erfüllt Modus/Datenklasse/Budget — Job bleibt lokal."""


class Scheduler:
    """Verteilt Jobs über die registrierten InferenceBackends.

    mode:   "stufe1" (Default — günstige On-Demand-Backends erlaubt) oder
            "stufe2" (EU-only — alle Nicht-EU-Backends gesperrt).
    burst_threshold: Queue-Tiefe, ab der Cloud-Bursting erlaubt ist.
    remote_first: bei True wird Remote vor local probiert (Tests/Admin).
    """

    def __init__(
        self,
        backends: list[InferenceBackend],
        mode: str = "stufe1",
        burst_threshold: int = 3,
        monthly_budget_usd: Optional[float] = None,
        remote_first: bool = False,
    ):
        self.backends = backends
        self.mode = mode
        self.burst_threshold = burst_threshold
        self.costs = CostTracker(monthly_budget_usd=monthly_budget_usd)
        self.remote_first = remote_first
        # Aktive, gemietete Instanzen (für den Watchdog)
        self._instances: dict[str, tuple[Instance, float]] = {}
        self._ttl_s = 7200  # Default-TTL: 2 h (Auto-Destroy-Watchdog)

    # ── Backend-Auswahl ───────────────────────────────────────────────────

    def _candidates(self, data_class: DataClass) -> list[InferenceBackend]:
        """Alle Backends, die Modus + Datenklasse erfüllen (geordnet)."""
        eu_only = self.mode == "stufe2"
        allowed = [
            b for b in self.backends
            if backend_allowed(b, data_class, eu_only)
        ]
        if self.remote_first:
            return sorted(allowed, key=lambda b: b.provider_name == "local")
        # Default: local zuerst (Jobs laufen wie heute auf der Box)
        return sorted(allowed, key=lambda b: b.provider_name != "local")

    def choose_backend(self, data_class: DataClass,
                       queue_depth: int) -> Optional[InferenceBackend]:
        """Backend für einen Job wählen.

        local bekommt den Job, solange die Queue nicht über der
        Burst-Schwelle liegt. Bei Engpass (queue_depth > burst_threshold)
        wird das erste Nicht-local-Backend gewählt — außer das Budget ist
        ausgeschöpft (dann bleibt es bei local, kein Bursting).
        """
        cands = self._candidates(data_class)
        if not cands:
            return None
        local = next((b for b in cands if b.provider_name == "local"), None)
        remote = next((b for b in cands if b.provider_name != "local"), None)

        if remote is not None and queue_depth > self.burst_threshold:
            if self.costs.over_budget():
                log.warning("Monatsbudget ausgeschöpft — kein Cloud-Bursting")
                return local
            return remote
        return local or remote

    # ── Job-Ausführung ────────────────────────────────────────────────────

    def run_job(
        self,
        job_payload: dict[str, Any],
        data_class: DataClass = DataClass.INTERNAL,
        queue_depth: int = 0,
        gpu_filter: Optional[GpuFilter] = None,
    ) -> JobResult:
        """Vollständiger Job über ein Backend (mieten → submit → poll → destroy).

        Wirft NoBackendAvailable, wenn kein Backend zulässig ist.
        Bei Remote-Fehlern wird die Instanz im finally destruiert (nie
        stoppen!) und der Fehler propagiert.
        """
        backend = self.choose_backend(data_class, queue_depth)
        if backend is None:
            raise NoBackendAvailable(
                f"kein Backend für data_class={data_class}, mode={self.mode}")

        flt = gpu_filter or GpuFilter(count=1)
        offers = backend.list_offers(flt)
        if not offers:
            raise NoBackendAvailable(
                f"{backend.provider_name}: keine passenden Angebote")

        instance: Optional[Instance] = None
        t0 = time.time()
        result = JobResult(status="failed", job_id="")
        try:
            instance = backend.acquire(
                offers[0], image=job_payload.get("image", ""),
                env=job_payload.get("env"))
            endpoint = backend.wait_ready(instance)
            job_id = backend.submit_job(endpoint, job_payload)
            # Poll bis done/failed (max. 30 min)
            deadline = time.time() + 1800
            result = JobResult(status="queued", job_id=job_id)
            while time.time() < deadline:
                result = backend.poll(instance, job_id)
                if result.status in ("done", "failed"):
                    break
                time.sleep(2)
            if result.status not in ("done", "failed"):
                result = JobResult(status="failed", job_id=job_id,
                                   error="Job-Timeout (30 min)")
        finally:
            if instance is not None:
                runtime_h = (time.time() - t0) / 3600
                offer = offers[0]
                cost_usd = offer.price_usd_h * runtime_h
                self.costs.record(JobCost(
                    job_id=result.job_id,
                    provider=backend.provider_name,
                    instance_id=instance.instance_id,
                    region=instance.region or offer.region,
                    price_usd_h=offer.price_usd_h,
                    runtime_h=runtime_h,
                ))
                log.info("Job %s auf %s: %s, Kosten ~%.4f $",
                         result.job_id, backend.provider_name,
                         result.status, cost_usd)
                self._forget(instance)
                backend.destroy(instance)
        return result

    # ── Auto-Destroy-Watchdog ─────────────────────────────────────────────

    def track(self, instance: Instance) -> None:
        """Instanz für den Watchdog registrieren (ts = jetzt)."""
        self._instances[instance.instance_id] = (instance, time.time())

    def _forget(self, instance: Instance) -> None:
        self._instances.pop(instance.instance_id, None)

    def destroy_stale(self, ttl_s: Optional[int] = None) -> list[str]:
        """Alle Instanzen destruieren, die älter als die TTL sind.

        Direkt per Provider-Destroy (DELETE) — greift auch, wenn die
        Orchestrierung ausgefallen ist (Spec-Szenario). Liefert die
        destruierten instance_ids.
        """
        ttl = ttl_s or self._ttl_s
        destroyed: list[str] = []
        for iid, (inst, ts) in list(self._instances.items()):
            if time.time() - ts > ttl:
                backend = next(
                    (b for b in self.backends
                     if b.provider_name == inst.provider), None)
                if backend is not None:
                    try:
                        backend.destroy(inst)
                        destroyed.append(iid)
                    except Exception:
                        log.exception("Watchdog-Destroy fehlgeschlagen: %s", iid)
                    finally:
                        self._forget(inst)
        return destroyed
