"""Change 238 — Wartungsauftrag: ausstehende Forced-Alignments nachziehen.

Befund 30.09.2026: Change 237 hat die Ursache behoben, aus der das
Hintergrund-Alignment seit Change 173 nie mehr automatisch eingereiht wurde.
Die Aufnahmen dieser Wochen stehen deshalb mit den groben Wortzeiten des
Transkriptionslaufs da (103 von 116 Aufnahmen ohne align-Job). Der
Wartungsauftrag zieht sie nach: als Scheduler-Task, gedrosselt, jederzeit
abbrechbar über die Auftragsdatei.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import align_backfill
from app.models import Job as JobRow
from app.models import Recording


@pytest.fixture(autouse=True)
def auftragsdatei(tmp_path, monkeypatch):
    """Auftragsdatei im tmp-Verzeichnis; Bilanz je Prüfung frisch."""
    align_backfill.reset_state()
    monkeypatch.setattr(align_backfill, "flag_path",
                        lambda data_dir=None: tmp_path / align_backfill.FLAG_NAME)
    yield
    align_backfill.reset_state()


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
                     status="queued"))
        s.commit()


def _auftrag(tmp_path):
    (tmp_path / align_backfill.FLAG_NAME).write_text("Wartungsauftrag")


# ---------------------------------------------------------------------------
# Auswahl und Auftragsdatei
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
    assert align_backfill.backfill_enabled() is False
    _auftrag(tmp_path)
    assert align_backfill.backfill_enabled() is True


# ---------------------------------------------------------------------------
# Takt
# ---------------------------------------------------------------------------


def test_ohne_auftragsdatei_tut_der_takt_nichts(db_env, monkeypatch):
    _rec(db_env, 1)
    gerufen = []
    monkeypatch.setattr("app.service._schedule_realign",
                        lambda *a, **k: gerufen.append(a) or True)

    assert align_backfill.tick() == 0
    assert gerufen == [], "ohne Auftragsdatei wird nichts eingereiht"


def test_takt_reiht_wellenweise_ein(db_env, tmp_path, monkeypatch):
    """Je Takt höchstens `limit` Aufträge, neueste zuerst, Priorität 1."""
    for rid in (1, 2, 3, 4, 5):
        _rec(db_env, rid)
    _auftrag(tmp_path)
    aufrufe = []

    def fake_schedule(rec_id, separate_backend="none", priority=0):
        aufrufe.append((rec_id, priority))
        _align_job(db_env, rec_id)   # wie der echte Pfad: die Job-Zeile entsteht
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)

    assert align_backfill.tick(2) == 2
    assert align_backfill.tick(2) == 2
    assert align_backfill.tick(2) == 1
    assert align_backfill.tick(2) == 0, "danach ist nichts mehr offen"

    assert [r for r, _ in aufrufe] == [5, 4, 3, 2, 1], "neueste zuerst"
    assert all(p == 1 for _, p in aufrufe), "Wartung läuft hinter der Nutzer-Arbeit"
    bilanz = align_backfill.status()
    assert bilanz["enqueued"] == 5
    assert bilanz["ohne_audio"] == []
    assert bilanz["aktiv"] is True


def test_aufnahme_ohne_audio_blockiert_die_wartung_nicht(db_env, tmp_path, monkeypatch):
    """Ohne Audio: einmal versuchen, merken, weiterziehen — sonst hinge der
    Task für immer an derselben Aufnahme."""
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

    assert align_backfill.tick(1) == 0     # zuerst kommt Aufnahme 2 dran
    assert align_backfill.tick(1) == 1     # dann Aufnahme 1
    assert align_backfill.tick(1) == 0

    assert versuche.count(2) == 1, "kein zweiter Versuch für dieselbe Aufnahme"
    assert align_backfill.status()["ohne_audio"] == [2]


def test_datei_loeschen_beendet_den_auftrag(db_env, tmp_path, monkeypatch):
    """Löschen der Auftragsdatei beendet die Wartung (Bilanz wird protokolliert)."""
    _rec(db_env, 1)
    _auftrag(tmp_path)
    monkeypatch.setattr("app.service._schedule_realign",
                        lambda rec_id, separate_backend="none", priority=0:
                        _align_job(db_env, rec_id) or True)

    assert align_backfill.tick(1) == 1
    assert align_backfill.status()["enqueued"] == 1

    (tmp_path / align_backfill.FLAG_NAME).unlink()
    assert align_backfill.tick(1) == 0
    assert align_backfill.status()["enqueued"] == 0, "Bilanz nach dem Ende zurückgesetzt"


# ---------------------------------------------------------------------------
# Registrierung in der Scheduler-Registry (kein eigener Thread)
# ---------------------------------------------------------------------------


def test_task_ist_im_scheduler_registriert():
    """Der Wartungsauftrag läuft als Scheduler-Task — nicht als nackter Thread
    (CI-Wächter: jeder `threading.Thread` in app/ braucht einen Zweck-Marker)."""
    from fastapi.testclient import TestClient

    import app.main as main_mod
    from app.scheduler import scheduler

    with TestClient(main_mod.app):
        assert "align-backfill" in scheduler.task_names()
