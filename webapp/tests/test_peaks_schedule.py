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
from sqlmodel import SQLModel, Session, create_engine, select

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
    from app import peaks as peaks_module

    monkeypatch.setattr(peaks_module, "compute_preview_path", lambda src: None)

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


def test_backfill_peaks_batch_seriell_ueber_alle_user(tmp_path, eng, monkeypatch):
    """Backfill-Loop: berechnet fehlende Peaks über ALLE User (auch anon),
    lässt vorhandene unangetastet, limitiert pro Durchlauf."""
    for uid, name in [("u1", "a.mp3"), (None, "anon.mp3"), ("u2", "b.mp3")]:
        audio = tmp_path / name
        audio.write_bytes(b"fake")
        with Session(eng) as s:
            rec = Recording(uid=uid, original_name=name, stored_path=str(audio),
                            status="done")
            s.add(rec)
            s.commit()
    # u2 hat schon Peaks + Preview — darf nicht angefasst werden
    with Session(eng) as s:
        rec = s.exec(
            select(Recording).where(Recording.original_name == "b.mp3")
        ).first()
        rec.waveform_peaks = [0.1, 0.2]
        rec.preview_path = str(tmp_path / "b_preview.mp3")
        s.add(rec)
        s.commit()

    calls: list[str] = []
    monkeypatch.setattr(svc, "_compute_peaks_path",
                        lambda path: calls.append(str(path)) or [0.5, 0.75])
    from app import peaks as peaks_module

    def fake_preview(src):
        p = Path(str(src).replace(".mp3", "") + "_preview.mp3")
        p.write_bytes(b"ID3fake")  # existierende Datei für stat()
        return p

    monkeypatch.setattr(peaks_module, "compute_preview_path", fake_preview)

    from app.routers import recordings as rec_routes

    n = rec_routes._backfill_peaks_batch(limit=2)
    assert n == 2  # nur die zwei ohne Assets, Limit greift
    assert len(calls) == 2
    assert any("a.mp3" in c for c in calls)
    assert any("anon.mp3" in c for c in calls)

    with Session(eng) as s:
        a = s.exec(select(Recording).where(Recording.original_name == "a.mp3")).first()
        anon = s.exec(select(Recording).where(Recording.original_name == "anon.mp3")).first()
        b = s.exec(select(Recording).where(Recording.original_name == "b.mp3")).first()
    assert a.waveform_peaks == [0.5, 0.75]
    assert anon.waveform_peaks == [0.5, 0.75]
    assert b.waveform_peaks == [0.1, 0.2]  # unangetastet
    # Preview-Sidecars wurden mitgeneriert
    assert a.preview_path and a.preview_path.endswith("a_preview.mp3")
    assert anon.preview_path and anon.preview_path.endswith("anon_preview.mp3")
    assert b.preview_path == str(tmp_path / "b_preview.mp3")


def test_backfill_peaks_batch_leere_peaks_kein_commit(tmp_path, eng, monkeypatch):
    """Decode-Fehler (leere Peaks) → kein Commit, kein Inflight-Hänger;
    beim nächsten Durchlauf wird erneut versucht."""
    audio = tmp_path / "kaputt.mp3"
    audio.write_bytes(b"fake")
    with Session(eng) as s:
        rec = Recording(uid="u9", original_name="kaputt.mp3",
                        stored_path=str(audio), status="done")
        s.add(rec)
        s.commit()

    monkeypatch.setattr(svc, "_compute_peaks_path", lambda path: [])
    from app import peaks as peaks_module

    monkeypatch.setattr(peaks_module, "compute_preview_path", lambda src: None)

    from app.routers import recordings as rec_routes

    n = rec_routes._backfill_peaks_batch(limit=5)
    assert n == 0
    with Session(eng) as s:
        r = s.get(Recording, 1)
    assert r is not None and r.waveform_peaks is None
    assert 1 not in rec_routes._peaks_inflight
