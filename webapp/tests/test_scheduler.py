"""Change 155 (Schritt 6): Scheduler-Registry — Registrierung, Intervall-
Ausführung, Fehler-Isolation, stop. Läuft komplett DB-frei."""

import threading
import time

import pytest


def _wait_for(fn, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.02)
    return False


def _make_scheduler():
    from app.scheduler import Scheduler

    return Scheduler()


def test_register_und_task_names():
    s = _make_scheduler()
    s.register("a", 60, lambda: None)
    s.register("b", 30, lambda: None)
    assert s.task_names() == ["a", "b"]
    s.unregister("a")
    assert s.task_names() == ["b"]


def test_register_ungueltiges_interval():
    s = _make_scheduler()
    with pytest.raises(ValueError):
        s.register("x", 0, lambda: None)


def test_task_laeuft_im_intervall():
    s = _make_scheduler()
    runs: list = []
    s.register("tick", 0.05, lambda: runs.append(time.monotonic()))
    s.start()
    try:
        assert _wait_for(lambda: len(runs) >= 2), "Task lief nie zweimal"
        # Der Task muss periodisch laufen (Abstand ~intervall, nicht einmalig)
        assert runs[-1] - runs[0] >= 0.03
    finally:
        s.stop()


def test_fehler_isoliert_task():
    """Ein werfender Task darf die anderen nicht stoppen (Registry-Logik)."""
    s = _make_scheduler()
    good_runs: list = []

    def bad():
        raise RuntimeError("kaputt")

    s.register("bad", 0.05, bad)
    s.register("good", 0.05, lambda: good_runs.append(time.monotonic()))
    s.start()
    try:
        assert _wait_for(lambda: len(good_runs) >= 2), \
            "gesunder Task lief nicht weiter trotz Fehler-Task"
    finally:
        s.stop()


def test_stop_beendet_loop():
    s = _make_scheduler()
    s.register("tick", 0.05, lambda: None)
    s.start()
    s.stop()
    time.sleep(0.15)
    assert not s._thread or not s._thread.is_alive(), \
        "Scheduler-Thread läuft nach stop weiter"


def test_start_idempotent():
    s = _make_scheduler()
    s.register("tick", 60, lambda: None)
    s.start()
    first = s._thread
    s.start()  # zweiter start darf keinen zweiten Thread machen
    assert s._thread is first
    s.stop()
