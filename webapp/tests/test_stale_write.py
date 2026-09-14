"""Change 189: optimistische Sperre beim vollen Listen-PUT.

Vorfall 14.09.2026 (Aufnahme 328): ein serverseitiger Reparaturschreibvorgang
wurde von einem offenen Browserfenster mit dessen geladenem Stand stillschweigend
überschrieben. Hier wird geprüft, dass ein veralteter Stand abgelehnt wird.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'stale.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


SEGMENTS = [{"start": 0.0, "end": 12.0, "text": "erster satz hier", "words": []}]


def _make_recording(client) -> str:
    resp = client.post("/api/recordings", files={"file": ("stale.mp3", b"fake", "audio/mpeg")})
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        rec.status = "done"
        rec.segments = SEGMENTS
        rec.text = SEGMENTS[0]["text"]
        s.add(rec)
        s.commit()
    return rid


def _set_updated_at(rid: str, when: dt.datetime) -> None:
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        rec.updated_at = when
        s.add(rec)
        s.commit()


def _load_updated_at(client, rid: str) -> str:
    return client.get(f"/api/recordings/{rid}").json()["updated_at"]


def test_veralteter_stand_wird_abgelehnt(client):
    rid = _make_recording(client)
    loaded = _load_updated_at(client, rid)
    # Serverseitige Änderung NACH dem Laden (z.B. Migration/Reparatur)
    _set_updated_at(rid, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30))

    neu = [{"start": 0.0, "end": 12.0, "text": "vom offenen fenster ueberschrieben", "words": []}]
    r = client.put(f"/api/recordings/{rid}/segments",
                   json={"segments": neu, "expected_updated_at": loaded})
    assert r.status_code == 409, r.text
    assert "stale_write" in r.text
    assert r.headers.get("x-current-updated-at")
    # Nichts geschrieben: Text unverändert, keine neue Version
    rec = client.get(f"/api/recordings/{rid}").json()
    assert rec["segments"][0]["text"] == SEGMENTS[0]["text"]
    assert len(client.get(f"/api/recordings/{rid}/versions").json()) == 0


def test_passender_stand_schreibt(client):
    rid = _make_recording(client)
    loaded = _load_updated_at(client, rid)
    neu = [{"start": 0.0, "end": 12.0, "text": "geaenderter satz", "words": []}]
    r = client.put(f"/api/recordings/{rid}/segments",
                   json={"segments": neu, "expected_updated_at": loaded})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/recordings/{rid}").json()["segments"][0]["text"] == "geaenderter satz"
    assert len(client.get(f"/api/recordings/{rid}/versions").json()) == 1


def test_ohne_feld_bleibt_kompatibel(client):
    rid = _make_recording(client)
    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": SEGMENTS})
    assert r.status_code == 200, r.text
