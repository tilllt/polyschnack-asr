"""dispatcher/costs.py — Kosten-Tracking + Monatsbudget (Change 020).

Spec: „Instanz-Hygiene und Kosten-Tracking" — der Dispatcher sammelt pro Job
Provider, Region, Laufzeit und geschätzte Kosten (Preis × Stunden) und
stoppt bei Überschreitung des Monatsbudgets das Cloud-Bursting.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobCost:
    """Eine abgerechnete Job-Kostenzeile (Audit-Log)."""

    job_id: str
    provider: str
    instance_id: str = ""
    region: str = ""
    price_usd_h: float = 0.0
    runtime_h: float = 0.0
    ts: float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        return self.price_usd_h * self.runtime_h


class CostTracker:
    """Sammelt Job-Kosten und prüft das Monatsbudget.

    Thread-safe (Queue-Worker laufen parallel). Das Budget ist ein
    rollierendes Fenster über die letzten 30 Tage (einfach, deterministisch).
    """

    def __init__(self, monthly_budget_usd: Optional[float] = None,
                 window_days: int = 30):
        self._budget = monthly_budget_usd
        self._window_s = window_days * 86400
        self._lock = threading.Lock()
        self._entries: list[JobCost] = []

    def record(self, cost: JobCost) -> None:
        with self._lock:
            self._entries.append(cost)
            cutoff = time.time() - self._window_s
            self._entries = [e for e in self._entries if e.ts >= cutoff]

    def spent_this_window(self) -> float:
        cutoff = time.time() - self._window_s
        with self._lock:
            return round(sum(
                e.cost_usd for e in self._entries if e.ts >= cutoff), 4)

    def over_budget(self) -> bool:
        if self._budget is None:
            return False
        return self.spent_this_window() >= self._budget

    def remaining(self) -> Optional[float]:
        if self._budget is None:
            return None
        return round(max(self._budget - self.spent_this_window(), 0.0), 4)

    def summary(self) -> dict:
        return {
            "budget_usd": self._budget,
            "spent_this_window_usd": self.spent_this_window(),
            "remaining_usd": self.remaining(),
            "over_budget": self.over_budget(),
            "jobs": len(self._entries),
        }
