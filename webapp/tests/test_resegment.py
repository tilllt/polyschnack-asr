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


def test_download_srt_with_max_duration(client):
    """max_duration_s am Download = Re-Segmentierung vor dem Export."""
    rid = _make_done_recording(client, [_seg(0, 10, _long_words())])

    r = client.get(f"/api/recordings/{rid}/download?format=srt&max_duration_s=4")
    assert r.status_code == 200, r.text
    cues = r.text.strip().split("\n\n")
    # Mehrere Cues statt einem 10-s-Block
    assert len(cues) > 1
    assert "charset=utf-8" in r.headers.get("content-type", "").lower()
