"""Change 187 — Migration: Grenzen aus Wörtern ableiten (plan/apply)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.bounds_migration import apply, plan
from app.models import Recording, TranscriptVersion


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'bounds.db'}")
    SQLModel.metadata.create_all(eng)
    return eng


def _words(spec, t0, step=0.5):
    out, t = [], t0
    for w in spec.split():
        out.append({"word": w, "start": round(t, 3), "end": round(t + step * 0.8, 3)})
        t += step
    return out


def _rec_drifted():
    """Live-Fall 328 verkürzt: gedriftete Grenzen + 14,5-s-Überlappung."""
    return Recording(
        uid="aa" * 16,
        original_name="podcast.m4a",
        stored_path="/data/audio/1/podcast.m4a",
        mime="audio/mp4",
        status="done",
        text="eins zwei drei vier fünf",
        segments=[
            {"start": 0.0, "end": 24.71, "text": "eins zwei drei", "words": _words("eins zwei drei", 0.24)},
            # Segmentgrenze ÜBERLAPPT Segment 0 um 9,7 s (Live-Fall 328: 14,5 s)
            {"start": 15.0, "end": 46.12, "text": "vier fünf", "words": _words("vier fünf", 12.0)},
        ],
    )


def _rec_with_empty_segment():
    return Recording(
        uid="bb" * 16,
        original_name="x.m4a",
        stored_path="/data/audio/1/x.m4a",
        mime="audio/mp4",
        status="done",
        text="eins zwei",
        segments=[
            # konsistent (Grenzen = Wortkanten) — nur das leere Segment fällt auf
            {"start": 0.2, "end": 0.92, "text": "eins zwei", "words": _words("eins zwei", 0.2, 0.4)},
            {"start": 5.0, "end": 9.0, "text": "", "words": []},
        ],
    )


def test_plan_meldet_drift_und_ueberlappung_ohne_zu_schreiben(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(_rec_drifted())
        s.commit()
        report = plan(s)
        assert report["recordings_actionable"] == 1
        assert report["overlaps_resolved"] == 1
        entry = report["recordings"][0]
        assert entry["segments_changed"] == 2
        assert entry["changes"][0]["end_after"] == 12.0     # Start des Folgeworts
        assert entry["changes"][0]["end_before"] == 24.71
        # nichts geschrieben
        rec = s.exec(select(Recording)).first()
        assert rec.segments[0]["end"] == 24.71
        assert s.exec(select(TranscriptVersion)).all() == []


def test_apply_zieht_grenzen_und_schreibt_version(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = _rec_drifted()
        s.add(rec)
        s.commit()
        report = apply(s)
        assert report["written"] == 1
        s.refresh(rec)
        segs = rec.segments
        assert segs[0]["start"] == 0.24            # erstes Wort
        assert segs[0]["end"] == segs[1]["start"]  # lückenlos, keine Überlappung
        assert segs[1]["end"] == segs[1]["words"][-1]["end"]
        # Text + Wortzahl unangetastet
        assert segs[0]["text"] == "eins zwei drei"
        assert sum(len(x["words"]) for x in segs) == 5
        versions = s.exec(select(TranscriptVersion)).all()
        assert len(versions) == 1 and versions[0].kind == "edit"


def test_apply_ist_idempotent(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(_rec_drifted())
        s.commit()
        assert apply(s)["written"] == 1
        second = apply(s)
        assert second["written"] == 0
        assert second["recordings"] == []


def test_segment_ohne_woerter_bleibt_unangetastet(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = _rec_with_empty_segment()
        s.add(rec)
        s.commit()
        apply(s)
        s.refresh(rec)
        empty = rec.segments[1]
        assert (empty["start"], empty["end"]) == (5.0, 9.0)


def test_uid_filter_grenzt_ein(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        s.add(_rec_drifted())
        s.add(_rec_with_empty_segment())
        s.commit()
        report = plan(s, uid="bb" * 16)
        assert report["recordings_actionable"] == 0      # nur leeres Segment
        report_all = plan(s)
        assert report_all["recordings_actionable"] == 1
