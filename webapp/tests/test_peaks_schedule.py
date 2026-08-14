"""Regression: _schedule_peaks funktioniert auch OHNE Event-Loop.

Die Routen sind sync (Starlette-Threadpool). Die erste Implementierung nutzte
asyncio.get_running_loop().create_task(...) — wirft dort immer RuntimeError,
die Peaks kamen nie an (Waveform blieb dauerhaft kaputt). Der Test startet
_schedule_peaks aus einem Plain-Thread und wartet auf das DB-Ergebnis.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app import db as db_module
from app import service as svc
from app.models import Recording
from app.routers import recordings as rec_routes


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'peaks.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


def test_schedule_peaks_thread_auch_ohne_event_loop(tmp_path, eng, monkeypatch):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    with Session(eng) as s:
        rec = Recording(uid="u1", original_name="a.mp3", stored_path=str(audio), status="uploaded")
        s.add(rec)
        s.commit()
        rid = rec.id

    monkeypatch.setattr(svc, "_compute_peaks_path", lambda path: [0.25, 0.5, 0.75])

    # Aus einem Plain-Thread aufrufen — genau wie der Starlette-Threadpool:
    # dort existiert kein asyncio-Event-Loop.
    import threading

    err: list[BaseException] = []

    def call():
        try:
            rec_routes._schedule_peaks(rid)
        except BaseException as exc:  # pragma: no cover
            err.append(exc)

    t = threading.Thread(target=call)
    t.start()
    t.join(timeout=10)
    assert not err, f"_schedule_peaks warf: {err}"

    for _ in range(50):
        with Session(eng) as s:
            r = s.get(Recording, rid)
            if r and r.waveform_peaks:
                break
        time.sleep(0.1)
    with Session(eng) as s:
        r = s.get(Recording, rid)
    assert r is not None
    assert r.waveform_peaks == [0.25, 0.5, 0.75]


def test_schedule_peaks_inflight_guard_kein_doppelthread(tmp_path, eng, monkeypatch):
    """Inflight-Guard: zweiter Aufruf bei laufender Berechnung startet keinen
    zweiten Thread (erkennbar an der Anzahl der _compute_peaks-Aufrufe)."""
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    with Session(eng) as s:
        rec = Recording(uid="u2", original_name="a.mp3", stored_path=str(audio), status="uploaded")
        s.add(rec)
        s.commit()
        rid = rec.id

    calls: list[str] = []
    import threading as _th

    gate = _th.Event()

    def slow_peaks(path):  # blockiert bis Gate geoeffnet
        calls.append("start")
        gate.wait(timeout=5)
        calls.append("end")
        return [1.0]

    monkeypatch.setattr(svc, "_compute_peaks_path", slow_peaks)

    rec_routes._schedule_peaks(rid)
    rec_routes._schedule_peaks(rid)  # zweiter Aufruf: Guard greift
    rec_routes._schedule_peaks(rid)  # dritter Aufruf: Guard greift
    time.sleep(0.3)  # Threads Zeit zum Starten geben
    gate.set()
    for _ in range(50):
        with Session(eng) as s:
            r = s.get(Recording, rid)
            if r and r.waveform_peaks:
                break
        time.sleep(0.1)
    assert calls.count("start") == 1, f"erwartet 1 Thread, sah {calls}"
    with Session(eng) as s:
        r = s.get(Recording, rid)
    assert r is not None and r.waveform_peaks == [1.0]
