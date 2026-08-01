"""Versions-Snapshots (Task A6) — Modell, snapshot(), get_diff()."""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Recording, TranscriptVersion, User
from app.versions import get_diff, list_versions, snapshot


@pytest.fixture
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="u1"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="done", text="Hallo Welt",
                        segments=[{"start": 0.0, "end": 1.0, "text": "Hallo Welt"}]))
        s.commit()
    return eng


def test_snapshot_creates_version(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        v = snapshot(s, rec, "transcribe", user_id=1)
        assert v.version_no == 1
        assert v.kind == "transcribe"
        assert v.text == "Hallo Welt"
        assert v.segments[0]["text"] == "Hallo Welt"
        assert v.created_by_user_id == 1


def test_second_snapshot_increments(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        snapshot(s, rec, "transcribe")
        rec.text = "Hallo Du"
        s.add(rec)
        s.commit()
        v2 = snapshot(s, rec, "edit")
        assert v2.version_no == 2
        assert v2.kind == "edit"


def test_snapshot_skips_empty(db):
    with Session(db) as s:
        rec = Recording(id=2, uid="r2", original_name="b.mp3", stored_path="p",
                        status="uploaded", text=None, segments=None)
        s.add(rec)
        s.commit()
        assert snapshot(s, rec, "transcribe") is None


def test_list_versions_ordered(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        snapshot(s, rec, "transcribe")
        rec.text = "X"
        s.add(rec)
        s.commit()
        snapshot(s, rec, "edit")
        vs = list_versions(s, 1)
        assert [v.version_no for v in vs] == [1, 2]


def test_diff_simple_edit(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        v1 = snapshot(s, rec, "transcribe")
        rec.text = "Hallo Du"
        s.add(rec)
        s.commit()
        v2 = snapshot(s, rec, "edit")
        diff = get_diff(v1, v2)
        assert {"type": "del", "text": "Hallo Welt"} in diff
        assert {"type": "add", "text": "Hallo Du"} in diff


def test_diff_identical_empty():
    from app.models import TranscriptVersion

    a = TranscriptVersion(text="Zeile\nZwei")
    b = TranscriptVersion(text="Zeile\nZwei")
    diff = get_diff(a, b)
    assert all(d["type"] == "same" for d in diff)
    assert len(diff) == 2


class _FakeRequest:
    def __init__(self, uid):
        self.session = {"user_id": uid}


def test_edit_creates_snapshot(db, monkeypatch):
    """PATCH segments → neue Version kind=edit."""
    from app.routers import segments

    monkeypatch.setattr(segments.settings, "OIDC_ENABLED", True)
    with Session(db) as s:
        d = segments.update_segment("r1", 0, segments.SegmentUpdate(text="Hallo Du"),
                                    _FakeRequest(1), s)
        assert d["segments"][0]["text"] == "Hallo Du"
        vs = list_versions(s, 1)
        assert len(vs) == 1 and vs[0].kind == "edit"
        assert vs[0].text == "Hallo Du"
