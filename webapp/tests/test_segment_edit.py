"""Editing & Save (PATCH /api/recordings/{rid}/segments/{idx}).

Sicherstellen: Nach einem Segment-Edit bleiben
  - Wörter MIT start/end (Karaoke-Visualisierung funktioniert weiter),
  - der Speaker erhalten (falls vorhanden),
  - rec.text konsistent mit den Segment-Texten,
  - Version-Snapshot "edit" wird erzeugt.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import Recording, User


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient mit OIDC-User + einer Recording mit 2 Segmenten.

    Eigene SQLite-DB pro Test (engine wird im app.db-Modul ersetzt, damit
    get_session dieselbe DB nutzt) — isoliert gegen andere Testmodule.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app import deps
    from app.identity import Identity
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'edit.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    with Session(eng) as s:
        s.add(User(id=77, sub="edit-tester", kind="oidc"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=9, uid="rec-edit-1", original_name="a.mp3",
            stored_path=str(audio), user_id=77, status="done",
            text="Hallo Welt zweiter Satz",
            segments=[
                {"start": 0.0, "end": 2.0, "text": "Hallo Welt",
                 "speaker": "SPEAKER_00",
                 "words": [
                     {"word": "Hallo", "start": 0.0, "end": 1.0},
                     {"word": "Welt", "start": 1.0, "end": 2.0},
                 ]},
                {"start": 2.0, "end": 4.0, "text": "zweiter Satz",
                 "speaker": "SPEAKER_01",
                 "words": [
                     {"word": "zweiter", "start": 2.0, "end": 3.0},
                     {"word": "Satz", "start": 3.0, "end": 4.0},
                 ]},
            ],
        ))
        s.commit()

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)

    def _fake_oidc(request, session):
        return Identity(User(id=77, sub="edit-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    # segments.py importiert current_identity aus app.identity
    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)

    with TestClient(app) as c:
        yield c


def test_edit_segment_updates_text_and_words(client):
    """Edit ersetzt text UND baut words mit start/end neu (Karaoke-fähig)."""
    r = client.patch("/api/recordings/rec-edit-1/segments/0",
                     json={"text": "Hallo Welt korrigiert"})
    assert r.status_code == 200
    body = r.json()
    seg = body["segments"][0]
    assert seg["text"] == "Hallo Welt korrigiert"
    assert len(seg["words"]) == 3  # 3 Wörter neu verteilt
    for w in seg["words"]:
        assert "start" in w and "end" in w
        assert w["end"] > w["start"]
    # Wörter liegen im Segment-Zeitfenster
    assert seg["words"][0]["start"] >= seg["start"]
    assert seg["words"][-1]["end"] <= seg["end"] + 1e-9


def test_edit_segment_preserves_speaker(client):
    """Der Speaker des Segments bleibt nach dem Edit erhalten."""
    r = client.patch("/api/recordings/rec-edit-1/segments/0",
                     json={"text": "Hallo neu"})
    assert r.status_code == 200
    seg = r.json()["segments"][0]
    assert seg["speaker"] == "SPEAKER_00"


def test_edit_segment_updates_recording_text(client):
    """rec.text wird aus allen Segment-Texten neu zusammengesetzt."""
    client.patch("/api/recordings/rec-edit-1/segments/0",
                 json={"text": "Hallo Welt korrigiert"})
    r = client.get("/api/recordings/rec-edit-1")
    assert r.status_code == 200
    assert r.json()["text"] == "Hallo Welt korrigiert zweiter Satz"


def test_edit_segment_creates_version_snapshot(client):
    """Nach dem Edit existiert eine 'edit'-Version (Versions-Historie)."""
    from sqlmodel import Session

    from app import db as db_module
    from app.versions import list_versions

    client.patch("/api/recordings/rec-edit-1/segments/0",
                 json={"text": "Hallo geändert"})
    with Session(db_module.engine) as s:
        kinds = [v.kind for v in list_versions(s, 9)]
    assert "edit" in kinds


def test_edit_segment_karaoke_words_have_distinct_timestamps(client):
    """Karaoke-Edge: Nach Edit haben alle Wörter aufsteigende, distinkte
    Timestamps — kein Wort mit start == end."""
    r = client.patch("/api/recordings/rec-edit-1/segments/1",
                     json={"text": "neuer Satz drei Worte"})
    assert r.status_code == 200
    words = r.json()["segments"][1]["words"]
    assert len(words) == 4
    for i, w in enumerate(words):
        assert w["end"] > w["start"]
        if i > 0:
            assert w["start"] >= words[i - 1]["end"] - 1e-9


def test_edit_segment_empty_text_400(client):
    r = client.patch("/api/recordings/rec-edit-1/segments/0",
                     json={"text": "   "})
    assert r.status_code == 400


def test_edit_segment_out_of_range_404(client):
    r = client.patch("/api/recordings/rec-edit-1/segments/99",
                     json={"text": "x"})
    assert r.status_code == 404


def test_edit_segment_anon_forbidden(client, monkeypatch):
    """Ohne Login (OIDC aktiv) → 401/403."""
    from app import deps
    import app.identity as identity_mod

    monkeypatch.setattr(deps, "current_identity",
                        lambda request, session: None)
    monkeypatch.setattr(identity_mod, "current_identity",
                        lambda request, session: None)
    r = client.patch("/api/recordings/rec-edit-1/segments/0",
                     json={"text": "x"})
    assert r.status_code in (401, 403)
