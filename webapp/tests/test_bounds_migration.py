"""Change 187 — Migration: Grenzen aus Wörtern ableiten (plan/apply)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.bounds_migration import apply, plan, words_look_real
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


def _irregular(start: float, n: int, gaps) -> list:
    """Wörter mit UNREGELMÄSSIGEN Abständen (echte Zeiten, kein Raster)."""
    out, t = [], start
    for i in range(n):
        dur = gaps[i % len(gaps)]
        out.append({"word": f"w{i}", "start": round(t, 3), "end": round(t + dur * 0.7, 3)})
        t += dur
    return out


def _rec_drifted():
    """Live-Fall 328 verkürzt: gedriftete Grenzen + Überlappung."""
    return Recording(
        uid="aa" * 16,
        original_name="podcast.m4a",
        stored_path="/data/audio/1/podcast.m4a",
        mime="audio/mp4",
        status="done",
        text="w0 w1 w2 w3 w4 w5 w6 w7 w8 w9",
        segments=[
            {"start": 0.0, "end": 24.71, "text": "w0 w1 w2 w3 w4",
             "words": _irregular(0.24, 5, [0.5, 0.8, 0.35, 0.62])},
            # Segmentgrenze ÜBERLAPPT Segment 0 um 9,7 s (Live-Fall 328: 14,5 s)
            {"start": 15.0, "end": 46.12, "text": "w5 w6 w7 w8 w9",
             "words": _irregular(12.0, 5, [0.44, 0.9, 0.3, 0.55])},
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
            {"start": 0.24, "end": 2.86, "text": "w0 w1 w2 w3 w4",
             "words": _irregular(0.24, 5, [0.5, 0.8, 0.35, 0.62])},
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
        assert segs[0]["start"] == 0.24            # erstes Wort (unverändert = Wortkante)
        assert segs[0]["end"] == segs[1]["start"]  # lückenlos, keine Überlappung
        assert segs[1]["end"] == segs[1]["words"][-1]["end"]
        # Text + Wortzahl unangetastet
        assert segs[0]["text"] == "w0 w1 w2 w3 w4"
        assert sum(len(x["words"]) for x in segs) == 10
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


def _rec_placeholder():
    """Segmente mit Platzhalter-Raster (Gleichverteilung) + gedrifteten Grenzen."""
    words = [
        {"word": f"w{i}", "start": 0.0 + i * 0.5, "end": 0.0 + (i + 1) * 0.5}
        for i in range(8)
    ]
    return Recording(
        uid="cc" * 16,
        original_name="alt.m4a",
        stored_path="/data/audio/1/alt.m4a",
        mime="audio/mp4",
        status="done",
        text=" ".join(w["word"] for w in words),
        segments=[{"start": 0.0, "end": 300.0, "text": " ".join(w["word"] for w in words),
                   "words": words}],
    )


def test_platzhalter_raster_wird_uebersprungen(tmp_path):
    """Change 187 (Prod-Dry-Run-Befund): Bei Backend-Platzhalter-Zeiten würde
    die Wortkanten-Regel Grenzen um Minuten verschieben — solche Aufnahmen
    werden ohne include_placeholders nicht angefasst."""
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = _rec_placeholder()
        s.add(rec)
        s.commit()
        assert words_look_real(rec.segments) is False
        report = plan(s)
        assert report["recordings_actionable"] == 0
        assert report["recordings_skipped_placeholder"] == 1
        assert apply(s)["written"] == 0
        s.refresh(rec)
        assert rec.segments[0]["end"] == 300.0
        # explizit erlaubt: dann greift die Regel
        forced = plan(s, include_placeholders=True)
        assert forced["recordings_actionable"] == 1


def test_echte_wortzeiten_gelten_als_echt(tmp_path):
    eng = _engine(tmp_path)
    with Session(eng) as s:
        rec = _rec_drifted()
        s.add(rec)
        s.commit()
        assert words_look_real(rec.segments) is True


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
