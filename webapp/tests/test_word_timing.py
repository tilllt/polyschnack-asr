"""Change 137: Manuelle Wort-Timing-Korrektur (Timing-Tab).

PATCH /api/recordings/{rid}/segments/{idx}/words/{word_idx}:
  - setzt start/end genau EINES Wortes + override=true,
  - leitet Segment-Grenzen aus erstem/letztem Wort neu ab,
  - validiert start<end, Mindestdauer 20 ms, Monotonie gegen Nachbarn,
  - erzeugt Versions-Snapshot "edit",
  - override:false (Reset) entfernt das Flag ohne Timing-Änderung.

Plus: Override-Überleben im Re-Align (restore_override_words) und im
Text-Edit (_align_words überträgt das Flag).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import Recording, User


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient mit OIDC-User + einer Recording mit 2 Segmenten."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app import deps
    from app.identity import Identity
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'timing.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    with Session(eng) as s:
        s.add(User(id=77, sub="timing-tester", kind="oidc"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"MP3")
        s.add(Recording(
            id=9, uid="rec-timing-1", original_name="a.mp3",
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
        return Identity(User(id=77, sub="timing-tester", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_oidc)
    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_oidc)

    with TestClient(app) as c:
        yield c


def test_patch_word_timing_sets_timing_override_and_boundaries(client):
    """Timing-Korrektur: start/end gesetzt, override=true, Segment-Ende folgt
    dem letzten Wort, rec.text unverändert, Nachbarwort unangetastet."""
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/1",
        json={"start": 1.2, "end": 1.9},
    )
    assert r.status_code == 200
    seg = r.json()["segments"][0]
    w = seg["words"][1]
    assert w["start"] == pytest.approx(1.2)
    assert w["end"] == pytest.approx(1.9)
    assert w["override"] is True
    # Segment-Grenzen aus erstem/letztem Wort: end folgt dem korrigierten Wort
    assert seg["end"] == pytest.approx(1.9)
    assert seg["start"] == pytest.approx(0.0)
    # Nachbarwort unverändert, Text unverändert
    assert seg["words"][0]["start"] == pytest.approx(0.0)
    assert seg["words"][0]["end"] == pytest.approx(1.0)
    assert seg["words"][0].get("override") is None
    assert r.json()["text"] == "Hallo Welt zweiter Satz"


def test_patch_word_timing_first_word_updates_segment_start(client):
    """Erstes Wort korrigiert → Segment-Start folgt ihm (Grenzen-Ableitung)."""
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/1/words/0",
        json={"start": 2.1, "end": 3.0},
    )
    assert r.status_code == 200
    seg = r.json()["segments"][1]
    assert seg["start"] == pytest.approx(2.1)
    assert seg["words"][0]["override"] is True


def test_patch_word_timing_cross_segment_monotonicity(client):
    """Monotonie gilt segmentübergreifend: Wort 0 von Segment 1 darf nicht
    vor das Ende des letzten Wortes von Segment 0 rutschen."""
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/1/words/0",
        json={"start": 0.5, "end": 1.5},
    )
    assert r.status_code == 400  # start < Ende von „Welt" (2.0)

    # ... aber eine Lücke (start >= prev end) ist erlaubt:
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/1/words/0",
        json={"start": 2.2, "end": 3.0},
    )
    assert r.status_code == 200


def test_patch_word_timing_rejects_start_gte_end(client):
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": 1.0, "end": 1.0},
    )
    assert r.status_code == 400


def test_patch_word_timing_rejects_min_duration(client):
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": 0.0, "end": 0.01},
    )
    assert r.status_code == 400


def test_patch_word_timing_rejects_overlap_into_next(client):
    """end darf den Start des nächsten Wortes nicht überschreiten."""
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": 0.0, "end": 1.5},
    )
    assert r.status_code == 400  # end 1.5 > nächster Wortstart 1.0


def test_patch_word_timing_rejects_partial_body(client):
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": 0.2},
    )
    assert r.status_code == 400


def test_patch_word_timing_rejects_empty_body(client):
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={},
    )
    assert r.status_code == 400


def test_patch_word_timing_rejects_non_finite(client):
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": "nan", "end": "1.0"},
    )
    assert r.status_code == 400


def test_patch_word_timing_404_wrong_indices(client):
    assert client.patch(
        "/api/recordings/rec-timing-1/segments/99/words/0",
        json={"start": 0.1, "end": 0.3},
    ).status_code == 404
    assert client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/99",
        json={"start": 0.1, "end": 0.3},
    ).status_code == 404


def test_patch_word_timing_creates_version_snapshot(client):
    from sqlmodel import Session

    from app import db as db_module
    from app.versions import list_versions

    client.patch("/api/recordings/rec-timing-1/segments/0/words/1",
                 json={"start": 1.3, "end": 1.9})
    with Session(db_module.engine) as s:
        kinds = [v.kind for v in list_versions(s, 9)]
    assert "edit" in kinds


def test_patch_word_timing_anon_forbidden(client, monkeypatch):
    from app import deps
    import app.identity as identity_mod

    monkeypatch.setattr(deps, "current_identity",
                        lambda request, session: None)
    monkeypatch.setattr(identity_mod, "current_identity",
                        lambda request, session: None)
    r = client.patch("/api/recordings/rec-timing-1/segments/0/words/0",
                     json={"start": 0.1, "end": 0.3})
    assert r.status_code in (401, 403)


def test_patch_word_timing_override_reset(client):
    """override:false entfernt das Flag — Timing bleibt stehen (bis zum
    nächsten Re-Align), keine Segment-Grenzen-Änderung."""
    client.patch("/api/recordings/rec-timing-1/segments/0/words/1",
                 json={"start": 1.2, "end": 1.9})
    r = client.patch("/api/recordings/rec-timing-1/segments/0/words/1",
                     json={"override": False})
    assert r.status_code == 200
    w = r.json()["segments"][0]["words"][1]
    assert w["start"] == pytest.approx(1.2)
    assert w["end"] == pytest.approx(1.9)
    assert w.get("override") is None


def test_patch_word_timing_timing_change_wins_over_override_false(client):
    """Timing-Änderung setzt override=true, auch wenn override:false im
    selben Request steht (Timing-Änderung ist die manuelle Korrektur)."""
    r = client.patch(
        "/api/recordings/rec-timing-1/segments/0/words/0",
        json={"start": 0.1, "end": 0.4, "override": False},
    )
    assert r.status_code == 200
    assert r.json()["segments"][0]["words"][0]["override"] is True


# ---------------------------------------------------------------------------
# Override-Überleben im Re-Align (restore_override_words / apply_aligned_words)
# ---------------------------------------------------------------------------


def test_restore_override_words_keeps_manual_timing():
    from app.service import restore_override_words

    old = [
        {"start": 0.0, "end": 2.0, "text": "Hallo Welt", "words": [
            {"word": "Hallo", "start": 0.0, "end": 1.0},
            {"word": "Welt", "start": 1.2, "end": 2.3, "override": True},
        ]},
    ]
    new_aligned = [
        {"start": 0.0, "end": 2.0, "text": "Hallo Welt", "words": [
            {"word": "Hallo", "start": 0.0, "end": 0.9},
            {"word": "Welt", "start": 0.9, "end": 1.8},
        ]},
    ]
    out = restore_override_words(old, new_aligned)
    w = out[0]["words"][1]
    assert w["start"] == pytest.approx(1.2)
    assert w["end"] == pytest.approx(2.3)
    assert w["override"] is True
    # Nicht-Override-Wort hat die frisch alignte Zeit bekommen
    assert out[0]["words"][0]["start"] == pytest.approx(0.0)
    assert out[0]["words"][0]["end"] == pytest.approx(0.9)
    assert out[0]["words"][0].get("override") is None


def test_restore_override_words_segment_boundaries_follow_restored_word():
    """Korrigiertes ERSTES Wort → Segment-Start folgt der manuellen Zeit."""
    from app.service import restore_override_words

    old = [
        {"start": 0.0, "end": 2.0, "text": "Hallo Welt", "words": [
            {"word": "Hallo", "start": 0.1, "end": 1.0, "override": True},
            {"word": "Welt", "start": 1.0, "end": 2.0},
        ]},
    ]
    new_aligned = [
        {"start": 0.0, "end": 2.0, "text": "Hallo Welt", "words": [
            {"word": "Hallo", "start": 0.0, "end": 0.9},
            {"word": "Welt", "start": 0.9, "end": 1.8},
        ]},
    ]
    out = restore_override_words(old, new_aligned)
    assert out[0]["start"] == pytest.approx(0.1)
    assert out[0]["words"][0]["start"] == pytest.approx(0.1)


def test_restore_override_words_drops_override_on_word_count_change():
    """Text geändert (Wortzahl weicht ab) → Override verworfen (kein Crash),
    die alignten Wörter bleiben komplett."""
    from app.service import restore_override_words

    old = [
        {"start": 0.0, "end": 2.0, "text": "Hallo Welt", "words": [
            {"word": "Hallo", "start": 0.0, "end": 1.0},
            {"word": "Welt", "start": 1.2, "end": 2.3, "override": True},
        ]},
    ]
    new_aligned = [
        {"start": 0.0, "end": 2.0, "text": "Hallo tolle Welt", "words": [
            {"word": "Hallo", "start": 0.0, "end": 0.6},
            {"word": "tolle", "start": 0.6, "end": 1.2},
            {"word": "Welt", "start": 1.2, "end": 1.8},
        ]},
    ]
    out = restore_override_words(old, new_aligned)
    assert len(out[0]["words"]) == 3
    assert out[0]["words"][2]["start"] == pytest.approx(1.2)
    assert out[0]["words"][2].get("override") is None


# ---------------------------------------------------------------------------
# Override überlebt Text-Edit (_align_words überträgt das Flag)
# ---------------------------------------------------------------------------


def test_align_words_keeps_override_flag():
    from app.routers.segments import _align_words

    old = [
        {"word": "Hallo", "start": 0.0, "end": 1.0},
        {"word": "Welt", "start": 1.2, "end": 2.3, "override": True},
    ]
    # 1:1 (Wort korrigieren): Flag bleibt
    out = _align_words(old, "Hallo Globus", 0.0, 2.0)
    assert out[1]["override"] is True
    assert out[1]["start"] == pytest.approx(1.2)
    # LCS-Match (Wort eingefügt): Flag bleibt am gematchten Wort
    out2 = _align_words(old, "Hallo schöne Welt", 0.0, 3.0)
    assert [w["word"] for w in out2] == ["Hallo", "schöne", "Welt"]
    assert out2[2]["override"] is True
    assert out2[2]["start"] == pytest.approx(1.2)
