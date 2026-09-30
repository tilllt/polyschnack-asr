"""Change 238 — Wartungsauftrag: ausstehende Forced-Alignments nachziehen.

Befund 30.09.2026: Change 237 hat die Ursache behoben, aus der das
Hintergrund-Alignment seit Change 173 nie mehr automatisch eingereiht wurde.
Die Aufnahmen dieser Wochen stehen deshalb mit den groben Wortzeiten des
Transkriptionslaufs da (103 von 116 Aufnahmen ohne align-Job). Der
Wartungsauftrag zieht sie nach — gedrosselt, in Wellen, abbrechbar.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import align_backfill
from app.models import Job as JobRow
from app.models import Recording


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    """Tmp-DB mit Job- und Recording-Tabelle (db.engine zur Laufzeit gepatcht)."""
    eng = create_engine(
        f"sqlite:///{tmp_path / 'backfill.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.db.engine", eng)
    return eng


def _rec(eng, rec_id: int, *, status: str = "done", alignment: str = "done") -> None:
    with Session(eng) as s:
        s.add(Recording(id=rec_id, uid=f"u{rec_id}", original_name=f"{rec_id}.mp3",
                        stored_path=f"/data/audio/{rec_id}.mp3", status=status,
                        alignment=alignment))
        s.commit()


def _align_job(eng, rec_id: int) -> None:
    with Session(eng) as s:
        s.add(JobRow(key=f"align-{rec_id}", rec_id=rec_id, kind="align",
                     status="done"))
        s.commit()


def _auftrag(tmp_path) -> Path:
    flag = tmp_path / align_backfill.FLAG_NAME
    flag.write_text("Wartungsauftrag")
    return flag


# ---------------------------------------------------------------------------
# Auswahl der Kandidaten
# ---------------------------------------------------------------------------


def test_kandidaten_nur_ohne_align_job(db_env):
    """Maßstab ist die Job-Tabelle, nicht das Feld `alignment`: das Feld steht
    auch dann auf „done", wenn nur die groben Wortzeiten existieren."""
    _rec(db_env, 1)
    _rec(db_env, 2)
    _rec(db_env, 3, status="processing")   # noch nicht fertig → kein Kandidat
    _rec(db_env, 4)
    _align_job(db_env, 4)                  # feines Alignment lief schon

    with Session(db_env) as s:
        ids = [r.id for r in align_backfill.candidates(s, limit=10)]

    assert ids == [2, 1], "neueste zuerst, nur fertige Aufnahmen ohne align-Job"


def test_flagdatei_steuert_den_auftrag(tmp_path):
    assert align_backfill.backfill_enabled(str(tmp_path)) is False
    _auftrag(tmp_path)
    assert align_backfill.backfill_enabled(str(tmp_path)) is True


# ---------------------------------------------------------------------------
# Ablauf: Wellen, Ende, Abbruch
# ---------------------------------------------------------------------------


def test_wellen_und_ende(db_env, tmp_path, monkeypatch):
    for rid in (1, 2, 3, 4, 5):
        _rec(db_env, rid)
    _auftrag(tmp_path)
    aufrufe = []

    def fake_schedule(rec_id, separate_backend="none", priority=0):
        aufrufe.append((rec_id, priority))
        _align_job(db_env, rec_id)   # wie der echte Pfad: die Job-Zeile entsteht
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)

    stats = align_backfill.run_backfill(wave=2, pause_s=0, data_dir=str(tmp_path))

    assert stats["enqueued"] == 5
    assert stats["ende"] == "nichts-mehr-offen"
    assert [r for r, _ in aufrufe] == [5, 4, 3, 2, 1], "neueste zuerst"
    assert all(p == 1 for _, p in aufrufe), "Wartung läuft hinter der Nutzer-Arbeit"


def test_abbruch_wenn_die_auftragsdatei_verschwindet(db_env, tmp_path, monkeypatch):
    """Löschen der Datei bricht ab — der Nutzer behält die Kontrolle."""
    for rid in (1, 2, 3):
        _rec(db_env, rid)
    flag = _auftrag(tmp_path)

    def fake_schedule(rec_id, separate_backend="none", priority=0):
        _align_job(db_env, rec_id)
        flag.unlink()
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)

    stats = align_backfill.run_backfill(wave=3, pause_s=0, data_dir=str(tmp_path))

    assert stats["ende"] == "abgebrochen"
    assert stats["enqueued"] == 1, "nach dem Abbruch wird nichts mehr eingereiht"


def test_ohne_audio_wird_nicht_wiederholt(db_env, tmp_path, monkeypatch):
    """Aufnahmen, deren Audio fehlt, dürfen die Schleife nicht endlos drehen."""
    _rec(db_env, 1)
    _rec(db_env, 2)   # Audio angeblich weg
    _auftrag(tmp_path)
    versuche = []

    def fake_schedule(rec_id, separate_backend="none", priority=0):
        versuche.append(rec_id)
        if rec_id == 2:
            return False
        _align_job(db_env, rec_id)
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)

    stats = align_backfill.run_backfill(wave=2, pause_s=0, data_dir=str(tmp_path))

    assert stats["ohne_audio"] == [2]
    assert versuche.count(2) == 1, "kein zweiter Versuch für dieselbe Aufnahme"
    assert stats["enqueued"] == 1
    assert stats["ende"] == "nichts-mehr-offen"


def test_obergrenze_beendet_den_lauf(db_env, tmp_path, monkeypatch):
    for rid in (1, 2, 3, 4):
        _rec(db_env, rid)
    _auftrag(tmp_path)

    def fake_schedule(rec_id, separate_backend="none", priority=0):
        _align_job(db_env, rec_id)
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)

    stats = align_backfill.run_backfill(wave=2, pause_s=0, max_total=2,
                                        data_dir=str(tmp_path))

    assert stats["enqueued"] == 2
    assert stats["ende"] == "obergrenze-erreicht"


def test_stop_event_bricht_ab(db_env, tmp_path, monkeypatch):
    import threading

    _rec(db_env, 1)
    _auftrag(tmp_path)
    stop = threading.Event()
    stop.set()

    stats = align_backfill.run_backfill(wave=2, pause_s=0, stop_event=stop,
                                        data_dir=str(tmp_path))

    assert stats["ende"] == "abgebrochen"
    assert stats["enqueued"] == 0


# ---------------------------------------------------------------------------
# Start über die Anwendung (nur mit Auftragsdatei)
# ---------------------------------------------------------------------------


def test_start_nur_mit_auftragsdatei(monkeypatch):
    """Der Wartungsauftrag läuft nur, wenn die Datei liegt — und dann wirklich."""
    from fastapi.testclient import TestClient

    import app.main as main_mod

    aufrufe = []
    monkeypatch.setattr(align_backfill, "run_backfill", lambda **kw: aufrufe.append(kw))

    flag = Path(os.environ["DATA_DIR"]) / align_backfill.FLAG_NAME
    flag.unlink(missing_ok=True)
    try:
        with TestClient(main_mod.app):
            time.sleep(0.1)
        assert aufrufe == [], "ohne Auftragsdatei startet nichts"

        flag.write_text("Wartungsauftrag")
        with TestClient(main_mod.app):
            for _ in range(100):
                if aufrufe:
                    break
                time.sleep(0.05)
        assert len(aufrufe) == 1, "mit Auftragsdatei startet der Lauf genau einmal"
    finally:
        flag.unlink(missing_ok=True)
