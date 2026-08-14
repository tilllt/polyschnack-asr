"""Regression: update_result darf vorhandene Waveform-Peaks NICHT mit None
ueberschreiben.

Seit 2026-08-14 berechnet der Worker keine Peaks mehr (der synchrone
Voll-Decode haengte lange Jobs nach der Align-Phase bei 99%) — die Peaks
kommen aus dem _schedule_peaks-Thread bzw. dem GET-Nachzug. Ein spaeteres
update_result mit waveform_peaks=None wuerde sonst die frisch gespeicherten
Peaks loeschen (kaputte Waveform nach Re-Transcribe).
"""
from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.crud import update_result
from app.models import Recording, User


def _engine(tmp_path: Path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3")
    with Session(eng) as s:
        s.add(User(id=1, sub="a", kind="oidc"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="processing",
                        waveform_peaks=[0.1, 0.2, 0.3]))
        s.commit()
    return eng


def test_update_result_none_behaelt_peaks(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = update_result(
            s, 1,
            status="done", text="hallo", duration_s=10.0, language="de",
            segments=None, processing_ms=1.0, error=None,
            waveform_peaks=None,  # Worker liefert keine Peaks mehr
        )
        assert rec.waveform_peaks == [0.1, 0.2, 0.3]


def test_update_result_leere_liste_ueberschreibt(tmp_path):
    """Eine leere Liste ist ein bewusster Wert (Berechnung lief, Ergebnis leer)."""
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = update_result(
            s, 1,
            status="done", text="hallo", duration_s=10.0, language="de",
            segments=None, processing_ms=1.0, error=None,
            waveform_peaks=[],
        )
        assert rec.waveform_peaks == []
