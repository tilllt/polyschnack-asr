"""Zugriffstests über die Routen (Task A4) — Shares wirken auf alle Endpunkte."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Recording, RecordingShare, User
from app.routers import recordings, segments, shares


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(segments.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3DATA")
    with Session(eng) as s:
        s.add(User(id=1, sub="owner", preferred_username="alice"))
        s.add(User(id=2, sub="other", preferred_username="bob"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="done",
                        text="Hallo", segments=[{"start": 0.0, "end": 1.0, "text": "Hallo"}]))
        s.add(Recording(id=2, uid="rpub", original_name="p.mp3",
                        stored_path=str(audio), user_id=None, status="done",
                        text="public", segments=[{"start": 0.0, "end": 1.0, "text": "public"}]))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def _add_share(eng, rec_id, user_id, level):
    with Session(eng) as s:
        s.add(RecordingShare(rec_id=rec_id, user_id=user_id, level=level))
        s.commit()


def test_share_read_can_get(db):
    _add_share(db, 1, 2, "read")
    with Session(db) as s:
        d = recordings.get_recording_endpoint("r1", _req(2), s)
        assert d["uid"] == "r1"


def test_no_share_forbidden(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_recording_endpoint("r1", _req(3), s)
        assert ei.value.status_code == 403


def test_share_read_cannot_edit(db):
    _add_share(db, 1, 2, "read")
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            segments.update_segment("r1", 0, segments.SegmentUpdate(text="X"),
                                    _req(2), s)
        assert ei.value.status_code == 403


def test_share_write_can_edit(db):
    _add_share(db, 1, 2, "write")
    with Session(db) as s:
        d = segments.update_segment("r1", 0, segments.SegmentUpdate(text="Geändert"),
                                    _req(2), s)
        assert d["segments"][0]["text"] == "Geändert"


def test_share_read_cannot_retranscribe(db, monkeypatch):
    _add_share(db, 1, 2, "read")
    called = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: called.append(a))
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.retranscribe("r1", recordings.RetranscribeParams(), _req(2), s)
        assert ei.value.status_code == 403
    assert not called


def test_share_full_can_delete(db, monkeypatch):
    _add_share(db, 1, 2, "full")
    with Session(db) as s:
        d = recordings.delete_recording_endpoint("r1", _req(2), s)
        assert d["deleted"] == "r1"
        assert s.get(Recording, 1) is None


def test_anonymous_cannot_touch_private(db):
    with Session(db) as s:
        with pytest.raises(HTTPException):
            recordings.get_recording_endpoint("r1", _req(None), s)


def test_legacy_public_readable_by_anonymous(db):
    with Session(db) as s:
        d = recordings.get_recording_endpoint("rpub", _req(None), s)
        assert d["uid"] == "rpub"


def test_legacy_public_not_editable_by_anonymous(db):
    # Teil-B-Semantik: public-Records sind read-only für Anonyme (Edit = write)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            segments.update_segment("rpub", 0, segments.SegmentUpdate(text="X"),
                                    _req(None), s)
        assert ei.value.status_code == 403


def test_owner_can_do_everything(db):
    with Session(db) as s:
        recordings.get_recording_endpoint("r1", _req(1), s)  # read ok
        segments.update_segment("r1", 0, segments.SegmentUpdate(text="Y"),
                                _req(1), s)  # write ok
