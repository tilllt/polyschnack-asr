"""Versions-API (Task A7) — Liste, Diff, Restore über die Routen."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import Recording, RecordingShare, User
from app.routers import versions as versions_router
from app.versions import list_versions, snapshot


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(versions_router.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(versions_router, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="a"))
        s.add(User(id=2, sub="b"))
        rec = Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="done", text="Zeile eins\nZeile zwei",
                        segments=[{"start": 0.0, "end": 1.0, "text": "Zeile eins\nZeile zwei"}])
        s.add(rec)
        s.commit()
        rec = s.get(Recording, 1)
        snapshot(s, rec, "transcribe", user_id=1)
        rec.text = "Zeile eins GEÄNDERT\nZeile zwei"
        s.add(rec)
        s.commit()
        snapshot(s, rec, "edit", user_id=1)
        s.add(RecordingShare(rec_id=1, user_id=2, level="read"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def test_list_versions(db):
    with Session(db) as s:
        lst = versions_router.list_versions_endpoint("r1", _req(1), s)
        assert [v["version_no"] for v in lst] == [1, 2]
        assert lst[1]["kind"] == "edit"


def test_list_requires_read(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            versions_router.list_versions_endpoint("r1", _req(99), s)
        assert ei.value.status_code == 403


def test_diff_between_versions(db):
    with Session(db) as s:
        d = versions_router.diff_endpoint("r1", 2, _req(1), s)
        assert d["from"] == 1 and d["to"] == 2
        assert {"type": "del", "text": "Zeile eins"} in d["diff"]
        assert {"type": "add", "text": "Zeile eins GEÄNDERT"} in d["diff"]


def test_diff_first_version_empty(db):
    with Session(db) as s:
        d = versions_router.diff_endpoint("r1", 1, _req(1), s)
        assert d["diff"] == []


def test_diff_unknown_version_404(db):
    with Session(db) as s:
        with pytest.raises(HTTPException):
            versions_router.diff_endpoint("r1", 99, _req(1), s)


def test_restore_sets_content_and_creates_version(db):
    with Session(db) as s:
        r = versions_router.restore_endpoint("r1", 1, _req(1), s)
        assert r["restored"] == 1
        rec = s.get(Recording, 1)
        assert rec.text == "Zeile eins\nZeile zwei"
        vs = list_versions(s, 1)
        assert vs[-1].kind == "restore"
        assert vs[-1].text == "Zeile eins\nZeile zwei"


def test_restore_requires_write(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:  # read-Share → kein Restore
            versions_router.restore_endpoint("r1", 1, _req(2), s)
        assert ei.value.status_code == 403
