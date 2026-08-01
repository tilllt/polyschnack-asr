"""Liste/Detail: Shares einbeziehen + access_level (Task A5)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.crud import list_recordings
from app.models import Recording, RecordingShare, User
from app.routers import recordings, segments, shares


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="a"))
        s.add(User(id=2, sub="b"))
        s.add(Recording(id=1, uid="own", original_name="own.mp3", stored_path="p",
                        user_id=1))
        s.add(Recording(id=2, uid="shared", original_name="shared.mp3", stored_path="p",
                        user_id=1))
        s.add(Recording(id=3, uid="theirs", original_name="theirs.mp3", stored_path="p",
                        user_id=2))
        s.add(Recording(id=4, uid="pub", original_name="pub.mp3", stored_path="p",
                        user_id=None))
        s.add(RecordingShare(rec_id=2, user_id=2, level="write"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def test_shared_records_appear_in_list(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=2)
        uids = {r.uid for r in rows}
        assert "shared" in uids       # geteilt mit user 2
        assert "theirs" in uids       # eigene
        assert "own" not in uids      # nicht geteilt
        assert "pub" not in uids      # OIDC-Modus: public nicht im privaten Space


def test_shared_records_marked_with_level(db):
    with Session(db) as s:
        lst = recordings.list_recordings_endpoint(q=None, request=_req(2), session=s)
        by_uid = {d["uid"]: d for d in lst}
        assert by_uid["shared"]["access_level"] == "write"
        assert by_uid["theirs"]["access_level"] == "full"


def test_own_records_are_full(db):
    with Session(db) as s:
        lst = recordings.list_recordings_endpoint(q=None, request=_req(1), session=s)
        by_uid = {d["uid"]: d for d in lst}
        assert by_uid["own"]["access_level"] == "full"
        assert by_uid["shared"]["access_level"] == "full"  # Owner bleibt Owner


def test_shared_space_anonymous_list(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=None)
        uids = {r.uid for r in rows}
        assert uids == {"pub"}


def test_get_includes_access_level(db):
    with Session(db) as s:
        d = recordings.get_recording_endpoint("shared", _req(2), s)
        assert d["access_level"] == "write"
