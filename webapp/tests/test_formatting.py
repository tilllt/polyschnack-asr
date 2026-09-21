"""Change 228 — KI-Formatierung: Vorgaben, Prompt-Schranke, Textfeld-Invariante.

Geprüft wird:
- Die Vorgaben liegen in allen drei Sprachen vor, „Stichwort-Protokoll" ist die
  Vorgabe und steht zuerst.
- Eine unbekannte Kennung fällt auf die Vorgabe zurück (kein Absturz).
- Eine eigene Vorlage schlägt die eingebaute Vorgabe; die Schranke („Erfinde
  nichts") hängt IMMER an — auch an eigenen Vorlagen.
- ``update_result`` schreibt den formatierten Text und räumt ihn wieder weg,
  wenn ein neuer Lauf ohne Formatierung durchläuft (kein veralteter Text).
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import formatting
from app.crud import update_result
from app.models import Recording


def test_presets_complete_and_default_first():
    keys = [p["key"] for p in formatting.preset_list()]
    assert keys[0] == "protocol"
    assert formatting.DEFAULT_PRESET == "protocol"
    assert len(keys) == len(set(keys))
    for p in formatting.preset_list():
        assert set(p["label"]) == {"de", "en", "pt"}, p["key"]
        assert set(p["note"]) == {"de", "en", "pt"}, p["key"]
        assert p["note"]["de"].strip(), p["key"]
    # Kein Prompt-Fließtext in der Oberflächen-Liste.
    assert all("prompt" not in p for p in formatting.preset_list())


def test_unknown_preset_falls_back_to_default():
    assert formatting.preset("gibts-nicht")["key"] == "protocol"
    assert formatting.preset(None)["key"] == "protocol"
    assert formatting.preset("")["key"] == "protocol"


def test_own_template_wins_and_guard_always_appended():
    std = formatting.build_prompt("summary", None)
    assert formatting.preset("summary")["prompt"].strip() in std
    assert formatting.GUARD in std

    own = formatting.build_prompt("protocol", "Meine eigene Anweisung")
    assert own.startswith("Meine eigene Anweisung")
    assert formatting.GUARD in own
    # Die eingebaute Vorgabe darf bei eigener Vorlage nicht mitlaufen.
    assert formatting.preset("protocol")["prompt"].strip() not in own

    # Leerraum ist keine eigene Vorlage.
    assert formatting.build_prompt("summary", "   ") == std


@pytest.fixture()
def db(tmp_path):
    # Datei-DB statt In-Memory: das Projekt startet Hintergrund-Threads
    # (Ausrichtung), die sonst „no such table" melden.
    eng = create_engine(f"sqlite:///{tmp_path/'fmt.db'}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", status="done",
                        stored_path=str(tmp_path / "a.mp3")))
        s.commit()
    return eng


def test_update_result_writes_formatted_text(db):
    with Session(db) as s:
        update_result(s, 1, status="done", text="wörtlich", duration_s=1.0,
                      language="de", segments=None, processing_ms=1.0, error=None,
                      formatted_text="Stichpunkt-Protokoll",
                      formatted_source="protocol")
        s.commit()
    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.text == "wörtlich"
        assert rec.formatted_text == "Stichpunkt-Protokoll"
        assert rec.formatted_source == "protocol"


def test_new_run_without_formatting_clears_old_text(db):
    with Session(db) as s:
        update_result(s, 1, status="done", text="wörtlich", duration_s=1.0,
                      language="de", segments=None, processing_ms=1.0, error=None,
                      formatted_text="alt", formatted_source="summary")
        s.commit()
    with Session(db) as s:
        update_result(s, 1, status="done", text="neu", duration_s=1.0,
                      language="de", segments=None, processing_ms=1.0, error=None)
        s.commit()
    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.formatted_text is None
        assert rec.formatted_source is None
        assert rec.text == "neu"


def test_run_carries_second_stage_fields():
    from app.models import TranscriptionRun

    run = TranscriptionRun(rec_id=1, enable_formatting=True, format_preset="tasks",
                           format_template_id=7, format_endpoint_id=8)
    assert (run.enable_formatting, run.format_preset) == (True, "tasks")
    assert (run.format_template_id, run.format_endpoint_id) == (7, 8)
    # Vorgabe ohne Angabe: Stufe aus, Protokoll-Vorgabe.
    run2 = TranscriptionRun(rec_id=2)
    assert run2.enable_formatting is False and run2.format_preset == "protocol"
