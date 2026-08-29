"""Change 155 (Schritt 6): Zentrale Scheduler-Registry.

Ersetzt die früheren einzelnen ``threading.Thread``-Loops im Lifespan
(main.py: retention-sweep, peaks-backfill) durch EINEN Scheduler-Thread,
der alle registrierten Tasks mit ihrem eigenen Intervall ausführt.

Tasks werden beim Start registriert (dict: Name → Intervall + Callable);
jeder Task läuft in der Reihenfolge seiner Fälligkeit (kein Overlap —
eine lange Laufzeit eines Tasks verschiebt die anderen nicht, der
Scheduler tickt unabhängig weiter und prüft Fälligkeiten).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("ps.scheduler")


class Scheduler:
    """Ein Thread, N registrierte periodische Tasks (Registry-Muster)."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register(self, name: str, interval_s: float, fn: Callable[[], Any],
                 description: str = "") -> None:
        """Task registrieren (Intervall in Sekunden). Ersetzt einen
        bestehenden Task mit demselben Namen (idempotent)."""
        if interval_s <= 0:
            raise ValueError(f"interval_s muss > 0 sein (Task {name!r})")
        self._tasks[name] = {
            "interval_s": float(interval_s),
            "fn": fn,
            "description": description,
            "next_run": time.monotonic() + float(interval_s),
        }
        log.info("Scheduler: Task %r registriert (alle %gs%s)",
                 name, interval_s, f" — {description}" if description else "")

    def unregister(self, name: str) -> None:
        self._tasks.pop(name, None)

    def task_names(self) -> list[str]:
        return sorted(self._tasks)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ps-scheduler",
        )
        self._thread.start()
        log.info("Scheduler: Thread gestartet (%d Task(s))", len(self._tasks))

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(1.0):
            now = time.monotonic()
            for name, task in list(self._tasks.items()):
                if task["next_run"] <= now:
                    task["next_run"] = now + task["interval_s"]
                    self._run_task(name, task)

    def _run_task(self, name: str, task: Dict[str, Any]) -> None:
        try:
            task["fn"]()
        except Exception:
            log.exception("Scheduler: Task %r fehlgeschlagen", name)


# Modul-Singleton (wie queue_manager): der Lifespan registriert + startet.
scheduler = Scheduler()
