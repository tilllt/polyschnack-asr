"""Feature 2026-08-15: Segmentlängen — Re-Segmentierung + PUT /segments.

- service.resegment_by_duration: ASR-Chunk-Segmente (~105 s) in Blöcke
  ≤ Ziel-Dauer aufteilen (Wort-Timestamps, Sprecher-Grenzen).
- PUT /api/recordings/{rid}/segments: Liste persistieren → Export nutzt
  dieselben Segmente wie die Preview.
"""
from __future__ import annotations

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

    eng = create_engine(f"sqlite:///{tmp_path / 'reseg.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _make_done_recording(client, segments) -> str:
    resp = client.post(
        "/api/recordings",
        files={"file": ("reseg-test.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = "done"
        rec.segments = segments
        rec.text = " ".join(str(x["text"]) for x in segments)
        s.add(rec)
        s.commit()
    return rid


def _seg(start: float, end: float, words: list[tuple[str, float, float]], speaker=None) -> dict:
    seg = {
        "start": start,
        "end": end,
        "text": " ".join(w[0] for w in words),
        "words": [{"word": w[0], "start": w[1], "end": w[2]} for w in words],
    }
    if speaker:
        seg["speaker"] = speaker
    return seg


# 10 Wörter à 1 s lückenlos ab 0 → ein 10-s-Segment
def _long_words() -> list[tuple[str, float, float]]:
    return [(f"w{i}", float(i), float(i + 1)) for i in range(10)]


def test_resegment_splits_by_duration():
    from app.service import resegment_by_duration

    segs = [_seg(0, 10, _long_words())]
    out = resegment_by_duration(segs, 4)
    assert len(out) > 1
    for s in out:
        assert s["end"] - s["start"] <= 4 + 1e-9
    # Nichts verloren, chronologisch lückenlos
    assert " ".join(s["text"] for s in out) == segs[0]["text"]
    for a, b in zip(out, out[1:]):
        assert b["start"] == pytest.approx(a["end"])


def test_resegment_desync_keeps_full_text():
    """Change 140 (User-Befund ec98bfdf): Weichen die Wörter vom Segment-
    Text ab (Aligner-Wörter decken den Text nicht ab), verteilt der Export
    den Segment-Text proportional über die Buckets — der Gesamttext bleibt
    EXAKT erhalten (vorher ging der nicht-abgedeckte Text verloren)."""
    from app.service import resegment_by_duration

    # Segment 0–10 s, Text hat 3 Sätze — die Wörter decken nur „abc" ab.
    seg = {
        "start": 0.0,
        "end": 10.0,
        "text": "abc def ghi",
        "words": [
            {"word": "abc", "start": 0.0, "end": 10.0},
        ],
    }
    out = resegment_by_duration([seg], 4)
    assert len(out) == 1  # ein Wort → ein Bucket (Mindest-1-Wort-Regel)
    assert out[0]["text"] == "abc def ghi"  # voller Text, nichts verloren


def test_resegment_desync_multi_bucket_keeps_full_text():
    """Mehrere Buckets bei Desync: die Bucket-Texte partitionieren den
    Segment-Text verlustfrei (proportional + letzter Bucket bekommt den
    Rest)."""
    from app.service import resegment_by_duration

    # 6 Wörter à 2 s (0–12 s), Text ist LÄNGER als der Wort-Join.
    seg = {
        "start": 0.0,
        "end": 12.0,
        "text": "eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf",
        "words": [{"word": f"w{i}", "start": float(i * 2), "end": float(i * 2 + 2)} for i in range(6)],
    }
    out = resegment_by_duration([seg], 4)
    assert len(out) >= 2
    joined = " ".join(s["text"] for s in out)
    # Gesamttext exakt erhalten (alle 12 Wörter des Segment-Texts)
    assert joined == seg["text"]


def test_resegment_speaker_boundary():
    from app.service import resegment_by_duration

    a = _seg(0, 2, [("hallo", 0, 1), ("du", 1, 2)], "SPEAKER_01")
    b = _seg(2, 4, [("ja", 2, 3), ("klar", 3, 4)], "SPEAKER_02")
    out = resegment_by_duration([a, b], 100)
    assert len(out) == 2  # Sprecher-Wechsel = Grenze trotz Dauer-Erlaubnis
    assert out[0]["speaker"] == "SPEAKER_01"
    assert out[1]["speaker"] == "SPEAKER_02"


def test_resegment_no_words_returns_original():
    from app.service import resegment_by_duration

    plain = [{"start": 0, "end": 5, "text": "nur text"}]
    assert resegment_by_duration(plain, 2) == plain


def test_resegment_manual_segments_stay_exact():
    from app.service import resegment_by_duration

    # Change 088: _manual:true (vom Frontend bei Grenz-Drag/Insert/Delete/
    # Split gesetzt) → Segment wandert UNVERÄNDERT durch, auch wenn es die
    # Ziel-Dauer überschreitet. Nur unmarkierte Segmente werden geteilt.
    manual = {**_seg(0, 10, _long_words()), "_manual": True}
    auto = _seg(0, 10, _long_words())
    out = resegment_by_duration([manual, auto], 4)
    assert out[0] is manual  # exakt dasselbe Dict-Objekt, unverändert
    assert out[0]["text"] == manual["text"]
    assert len(out[1:]) > 1  # das unmarkierte Riesen-Segment wurde geteilt
    for s in out[1:]:
        assert s["end"] - s["start"] <= 4 + 1e-9


def test_resegment_manual_position_preserved():
    from app.service import resegment_by_duration

    # Reihenfolge bleibt: manuelles Segment zwischen zwei geteilten Chunks.
    manual = {**_seg(4, 14, _long_words()), "_manual": True}
    out = resegment_by_duration(
        [_seg(0, 4, [("x", 0, 4)]), manual, _seg(14, 18, [("y", 14, 18)])], 4
    )
    assert out[0]["text"] == "x"
    assert out[1] is manual
    assert out[2]["text"] == "y"


def test_put_segments_persists_and_rebuilds_text(client):
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])

    # Erst eine Re-Segmentierung, dann per PUT persistieren
    from app.service import resegment_by_duration

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        new_segs = resegment_by_duration(rec.segments, 4)

    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": new_segs})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["segments"]) > 1
    # Text aus Segment-Texten neu gebaut
    assert body["text"] == " ".join(s["text"] for s in new_segs)

    # Persistiert? (Export würde jetzt dieselben Segmente liefern)
    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert len(rec.segments) == len(new_segs)


def test_put_segments_validation(client):
    rid = _make_done_recording(client, [_seg(0, 2, [("a", 0, 1), ("b", 1, 2)])])

    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": []})
    assert r.status_code == 400

    r = client.put(
        f"/api/recordings/{rid}/segments",
        json={"segments": [{"start": 0, "end": 2, "text": ""}]},
    )
    assert r.status_code == 400

    r = client.put(
        f"/api/recordings/{rid}/segments",
        json={"segments": [{"end": 2, "text": "kein start"}]},
    )
    assert r.status_code == 400


def test_put_segments_sets_manual_flag(client):
    """Change 009: PUT /segments markiert die Aufteilung als manuell —
    Antwort UND DB tragen segments_manual == true (Anzeige nutzt segments
    direkt, keine erneute Re-Segmentierung nach segMaxDuration)."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec.segments_manual is False  # Default: Auto-Aufteilung

    r = client.put(f"/api/recordings/{rid}/segments",
                   json={"segments": [_seg(0, 10, _long_words())]})
    assert r.status_code == 200, r.text
    assert r.json()["segments_manual"] is True

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec.segments_manual is True  # persistiert


def test_restore_resets_manual_flag(client):
    """Change 009: Restore stellt einen alten ASR-Stand wieder her →
    segments_manual = false (Auto-Aufteilung gilt wieder)."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])
    # Erst manuell markieren (PUT), dann eine Version anlegen, die wir
    # zurückholen können (Snapshot beim PUT = kind edit reicht).
    client.put(f"/api/recordings/{rid}/segments",
               json={"segments": [_seg(0, 4, [("a", 0, 1), ("b", 1, 2)])]})

    from app.db import engine
    from app.models import Recording, TranscriptVersion
    from app.versions import list_versions
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec.segments_manual is True
        versions = list_versions(s, rec.id)
        # Letzte Version ist der manuelle Stand (kind=edit)
        target = versions[-1].version_no

    r = client.post(f"/api/recordings/{rid}/versions/{target}/restore")
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec.segments_manual is False  # zurückgesetzt


def test_download_srt_with_max_duration(client):
    """max_duration_s am Download = Re-Segmentierung vor dem Export."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])

    r = client.get(f"/api/recordings/{rid}/download?format=srt&max_duration_s=4")
    assert r.status_code == 200, r.text
    cues = r.text.strip().split("\n\n")
    # Mehrere Cues statt einem 10-s-Block
    assert len(cues) > 1
    assert "charset=utf-8" in r.headers.get("content-type", "").lower()


def _count_versions(rid: str) -> int:
    from app.db import engine
    from app.models import Recording, TranscriptVersion
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        return len(
            s.exec(
                select(TranscriptVersion).where(TranscriptVersion.rec_id == rec.id)
            ).all()
        )


def test_put_segments_create_version_false_no_snapshot(client):
    """Change 068: Autosave (create_version=false) schreibt die Segmente,
    aber erzeugt KEINE neue TranscriptVersion — die Version entsteht erst
    beim Verlassen des Edit-Mode (create_version=True, Default)."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])
    before = _count_versions(rid)

    r = client.put(
        f"/api/recordings/{rid}/segments?create_version=false",
        json={"segments": [_seg(0, 10, _long_words())]},
    )
    assert r.status_code == 200, r.text
    # DB-Stand ist aktuell, aber keine neue Version
    assert _count_versions(rid) == before

    # Default (True) erzeugt eine Version
    r = client.put(
        f"/api/recordings/{rid}/segments",
        json={"segments": [_seg(0, 10, _long_words())]},
    )
    assert r.status_code == 200, r.text
    assert _count_versions(rid) == before + 1


def test_put_segments_create_version_false_still_persists(client):
    """Change 068: Auch ohne Version ist der Write atomar persistiert —
    der Text ist in der DB, obwohl keine TranscriptVersion angelegt wurde."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])
    new_text = "Autosave hat diesen Text atomar gespeichert"
    r = client.put(
        f"/api/recordings/{rid}/segments?create_version=false",
        json={"segments": [{"start": 0, "end": 10, "text": new_text}]},
    )
    assert r.status_code == 200, r.text

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec.text == new_text
