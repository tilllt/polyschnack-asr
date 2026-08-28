"""Speaker-Rename: POST /api/recordings/{rid}/speaker-rename.

Ersetzt das speaker-Feld in ALLEN Segmenten (User-Anforderung: Doppelklick
auf einen Speaker-Namen → umbenennen → gilt an allen Vorkommen). Muster aus
test_segment_edit.py: eigene SQLite-DB, OIDC-User, Identity-Mocks an beiden
Import-Stellen (app.deps + app.identity).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import Recording, User


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app import deps
    from app.identity import Identity
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'rename.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    with Session(eng) as s:
        s.add(User(id=77, sub="rename-tester", kind="oidc"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=9, uid="rec-rename-1", original_name="a.mp3",
            stored_path=str(audio), user_id=77, status="done",
            text="a b c",
            segments=[
                {"start": 0.0, "end": 1.0, "text": "a", "speaker": "SPEAKER_00",
                 "words": [{"word": "a", "start": 0.0, "end": 1.0}]},
                {"start": 1.0, "end": 2.0, "text": "b", "speaker": "SPEAKER_01",
                 "words": [{"word": "b", "start": 1.0, "end": 2.0}]},
                {"start": 2.0, "end": 3.0, "text": "c", "speaker": "SPEAKER_00",
                 "words": [{"word": "c", "start": 2.0, "end": 3.0}]},
            ],
        ))
        s.commit()

    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", True)

    def _fake_oidc(request, session):
        return Identity(User(id=77, sub="rename-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)

    with TestClient(app) as c:
        yield c


def test_rename_speaker_updates_all_segments(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    assert r.status_code == 200
    body = r.json()
    renamed = [s for s in body["segments"] if s["text"] in ("a", "c")]
    assert all(s["speaker"] == "Anna" for s in renamed)
    assert body["renamed"] == 2
    # Der andere Speaker bleibt unverändert
    other = [s for s in body["segments"] if s["text"] == "b"]
    assert other[0]["speaker"] == "SPEAKER_01"


def test_rename_speaker_unknown_returns_400(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_99", "to_speaker": "X"})
    assert r.status_code == 400


def test_rename_speaker_requires_auth(client, monkeypatch):
    from app import deps
    import app.identity as identity_mod

    monkeypatch.setattr(deps, "current_identity", lambda request, session: None)
    monkeypatch.setattr(identity_mod, "current_identity", lambda request, session: None)
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    assert r.status_code in (401, 403)


def test_rename_speaker_snapshots_version(client):
    from sqlmodel import Session

    from app import db as db_module
    from app.versions import list_versions

    client.post("/api/recordings/rec-rename-1/speaker-rename",
                json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    with Session(db_module.engine) as s:
        kinds = [v.kind for v in list_versions(s, 9)]
    assert "edit" in kinds


def test_rename_speaker_persists_after_reload(client):
    """Der neue Name steht auch in rec.segments (DB), nicht nur in der Antwort."""
    client.post("/api/recordings/rec-rename-1/speaker-rename",
                json={"from_speaker": "SPEAKER_00", "to_speaker": "Bernd"})
    r = client.get("/api/recordings/rec-rename-1")
    assert r.status_code == 200
    segs = r.json()["segments"]
    assert all(s["speaker"] == "Bernd" for s in segs if s["text"] in ("a", "c"))


def test_rename_speaker_empty_names_400(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": " ", "to_speaker": "Anna"})
    assert r.status_code == 400


# ── Change 138: tolerantes Matching (SPEAKER_01 ↔ SPEAKER_1 ↔ 01 ↔ 1) ──


def test_rename_speaker_one_digit_matches(client):
    """from_speaker 'SPEAKER_1' (einstellig) renamed 'SPEAKER_01'-Segmente —
    exakter Vergleich gab vorher 400 („SPEAKER_01 not found")."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_1", "to_speaker": "Mutter"})
    assert r.status_code == 200
    body = r.json()
    assert body["renamed"] == 1
    seg_b = [s for s in body["segments"] if s["text"] == "b"][0]
    assert seg_b["speaker"] == "Mutter"
    # andere Segmente unangetastet
    assert [s["speaker"] for s in body["segments"] if s["text"] != "b"] == [
        "SPEAKER_00", "SPEAKER_00"]


def test_rename_speaker_bare_number_matches(client):
    """from_speaker '01' (ohne Präfix) matcht 'SPEAKER_01'."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "01", "to_speaker": "Mutter"})
    assert r.status_code == 200
    assert r.json()["renamed"] == 1


def test_rename_speaker_case_insensitive(client):
    """from_speaker 'speaker_01' (klein) matcht 'SPEAKER_01'."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "speaker_01", "to_speaker": "Mutter"})
    assert r.status_code == 200
    assert r.json()["renamed"] == 1


def test_rename_speaker_letter_label_matches(client):
    """Buchstabe 'B' → Sprecher 1 → matcht 'SPEAKER_01' (CrispASR-Format)."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "B", "to_speaker": "Mutter"})
    assert r.status_code == 200
    assert r.json()["renamed"] == 1


def test_rename_speaker_without_number_400(client):
    """Kein Nummern-/Buchstaben-Key → klare 400 statt 'not found'."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "???", "to_speaker": "Anna"})
    assert r.status_code == 400
    assert "number or letter" in r.json()["detail"]


def test_rename_speaker_unknown_number_still_400(client):
    """Nummer, die in KEINEM Segment vorkommt → weiterhin 400 (ehrlich)."""
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_07", "to_speaker": "Anna"})
    assert r.status_code == 400


# ── Change 140: sauberes, vollständiges Parsen (kein Substring-Match) ──


def test_rename_speaker_one_never_matches_eleven(client):
    """„SPEAKER_1" (Sprecher 1) darf NIE „SPEAKER_11"-Segmente treffen —
    die Nummer wird vollständig geparst (kein Substring „1" in „11")."""
    from sqlmodel import Session

    from app import db as db_module

    # Segmente mit SPEAKER_00 + SPEAKER_01 + SPEAKER_11 anlegen (tiefe Kopie!)
    import json as _json

    with Session(db_module.engine) as s:
        from app.models import Recording

        rec = s.get(Recording, 9)
        segs = _json.loads(_json.dumps(rec.segments or []))
        segs[2]["speaker"] = "SPEAKER_11"  # text „c" → Sprecher 11
        rec.segments = segs
        s.add(rec)
        s.commit()
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_1", "to_speaker": "Mutter"})
    assert r.status_code == 200
    assert r.json()["renamed"] == 1  # NUR der SPEAKER_01-Block (text „b")
    renamed = [s["text"] for s in r.json()["segments"] if s["speaker"] == "Mutter"]
    assert renamed == ["b"]
    # SPEAKER_11 bleibt unangetastet
    sp11 = [s["speaker"] for s in r.json()["segments"] if s["text"] == "c"]
    assert sp11 == ["SPEAKER_11"]


def test_rename_speaker_broken_label_no_match(client):
    """Kaputte Labels (SPEAKER_A, SPEAKER_1X) matchen NIE — kein falsches
    Umbenennen über Substring- oder Buchstaben-Fallback."""
    for bad in ("SPEAKER_A", "SPEAKER_1X"):
        r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                        json={"from_speaker": bad, "to_speaker": "Anna"})
        assert r.status_code == 400, f"{bad} hätte 400 geben müssen"


def test_rename_speaker_naked_number_matches_only_own(client):
    """Nackte „1" matcht SPEAKER_01 — aber nicht SPEAKER_11."""
    from sqlmodel import Session

    from app import db as db_module

    import json as _json

    with Session(db_module.engine) as s:
        from app.models import Recording

        rec = s.get(Recording, 9)
        segs = _json.loads(_json.dumps(rec.segments or []))
        segs[0]["speaker"] = "SPEAKER_11"
        rec.segments = segs
        s.add(rec)
        s.commit()
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "1", "to_speaker": "Mutter"})
    assert r.status_code == 200
    assert r.json()["renamed"] == 1  # nur SPEAKER_01 (text „b")


def test_rename_speaker_zero_matches_empty_speaker(client, monkeypatch):
    """Segmente OHNE speaker-Feld werden von 'SPEAKER_00' NICHT erfasst
    (kein stiller Fallback auf SPEAKER_00 beim Matching)."""
    from sqlmodel import Session

    from app import db as db_module

    client.post("/api/recordings/rec-rename-1/speaker-rename",
                json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    # Alle drei Segmente umbenannt (00 matcht 00) — Baseline ok; jetzt
    # Segmente ohne speaker bauen und prüfen, dass sie NICHT matchen:
    with Session(db_module.engine) as s:
        from app.models import Recording

        rec = s.get(Recording, 9)
        # Tiefe Kopie nötig — In-Place-Mutation der JSON-Liste umgeht die
        # SQLAlchemy-Änderungserkennung (bekanntes Muster, s. segments.py).
        import json as _json

        segs = _json.loads(_json.dumps(rec.segments or []))
        for seg in segs:
            seg.pop("speaker", None)
        rec.segments = segs
        s.add(rec)
        s.commit()
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "Anna"})
    assert r.status_code == 400  # kein Segment hat einen Speaker → kein Match


def test_rename_speaker_empty_to_400(client):
    r = client.post("/api/recordings/rec-rename-1/speaker-rename",
                    json={"from_speaker": "SPEAKER_00", "to_speaker": "  "})
    assert r.status_code == 400
