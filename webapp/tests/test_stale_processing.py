"""Stale-Processing-Watchdog: hängengebliebene Transkriptionen → failed.

Regression 2026-08-14 (User-Befund): Live-Modus blieb bei 80% / „processing"
hängen, weil der Worker nach einem OOM-Kill oder einer abgerissenen
SSE-Verbindung nie ein Status-Update schrieb. Der Sweep erkennt verwaiste
processing-Recordings an ihrem veralteten updated_at.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app import db as db_module
from app.models import Recording
from app.stale_jobs import sweep_stale_processing


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'stale.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


def _rec(uid: str, status: str, updated_hours_ago: float, note: str | None = None) -> Recording:
    return Recording(
        uid=uid,
        original_name="a.mp3",
        stored_path="/tmp/x.mp3",
        status=status,
        progress_note=note,
        updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=updated_hours_ago),
    )


def test_sweep_markiert_nur_alte_processing_ohne_diar(eng):
    with Session(eng) as s:
        s.add(_rec("alt", "processing", 5.0))                     # alt → failed
        s.add(_rec("frisch", "processing", 0.0))                  # frisch → bleibt
        s.add(_rec("diar", "processing", 5.0, note="diarization"))  # aktive Diar → bleibt
        s.add(_rec("done", "done", 5.0))                          # done → unberührt
        s.add(_rec("failed", "failed", 5.0))                      # failed → unberührt
        s.add(_rec("queued", "queued", 5.0))                      # queued → unberührt
        s.commit()

    with Session(eng) as s:
        assert sweep_stale_processing(s) == 1
        s.commit()

    with Session(eng) as s:
        rows = {r.uid: r for r in s.query(Recording).all()}

    assert rows["alt"].status == "failed"
    assert "unterbrochen" in (rows["alt"].error or "")
    assert rows["frisch"].status == "processing"
    assert rows["diar"].status == "processing"
    assert rows["done"].status == "done"
    assert rows["failed"].status == "failed"
    assert rows["queued"].status == "queued"


def test_sweep_grenze_konfigurierbar(eng, monkeypatch):
    import app.stale_jobs as sj

    monkeypatch.setattr(sj, "STALE_PROCESSING_MINUTES", 1)
    with Session(eng) as s:
        s.add(_rec("alt", "processing", 0.02))  # 1,2 min alt → über 1-min-Grenze
        s.commit()
    with Session(eng) as s:
        assert sweep_stale_processing(s) == 1


def test_sweep_ueberspringt_diar_mit_prozentnote(eng):
    """Change 162: progress_note trägt seit Change 150/151 den Prozentwert
    ('diarization 42%'). Der alte Exakt-Vergleich ('== \"diarization\"')
    hätte die laufende Diarization als stale markiert — Präfix-Vergleich
    lässt sie laufen."""
    with Session(eng) as s:
        s.add(_rec("diar42", "processing", 5.0, note="diarization 42%"))
        s.add(_rec("diar0", "processing", 5.0, note="diarization 0%"))
        s.add(_rec("alt", "processing", 5.0))  # ohne Note → failed
        s.commit()

    with Session(eng) as s:
        assert sweep_stale_processing(s) == 1
        s.commit()

    with Session(eng) as s:
        rows = {r.uid: r for r in s.query(Recording).all()}
    assert rows["diar42"].status == "processing"
    assert rows["diar0"].status == "processing"
    assert rows["alt"].status == "failed"
