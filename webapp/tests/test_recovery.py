"""Recovery-Router — verwaiste Aufnahmen finden + wiederherstellen."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import Recording, User
from app.routers import recovery


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    # OIDC an + Admin-Session
    monkeypatch.setattr(recovery.settings, "OIDC_ENABLED", True)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "audio"
    audio.mkdir()
    monkeypatch.setattr(recovery.settings, "AUDIO_DIR", audio)
    with Session(eng) as s:
        s.add(User(id=1, sub="admin", kind="oidc"))
        s.commit()
    return eng


def _admin_req():
    return _FakeRequest(session={"is_admin": True})


def _nonadmin_req():
    return _FakeRequest(session={})


def _touch(path: Path, age_s: float = 0.0):
    path.write_bytes(b"RIFF fake audio " + path.name.encode()[:8])
    old = time.time() - age_s
    os.utime(path, (old, old))


def test_scan_finds_orphan(db):
    audio = recovery.settings.AUDIO_DIR
    _touch(audio / "orphan_1.webm", age_s=3600)
    _touch(audio / "orphan_2.ogg", age_s=7200)
    with Session(db) as s:
        # eine referenzierte Datei (kein Orphan)
        ref = audio / "referenced.wav"
        _touch(ref, age_s=3600)
        s.add(Recording(id=1, uid="r1", original_name="ref.wav",
                        stored_path=str(ref), user_id=1,
                        status="done", text="Hallo"))
        s.commit()
        res = recovery.recovery_scan(_admin_req(), s)
    assert res["count"] == 2
    names = {o["filename"] for o in res["orphans"]}
    assert names == {"orphan_1.webm", "orphan_2.ogg"}
    by_age = {o["filename"]: o for o in res["orphans"]}
    assert by_age["orphan_1.webm"]["age_s"] >= 3600
    # älteste zuerst
    assert res["orphans"][0]["filename"] == "orphan_2.ogg"


def test_scan_skips_fresh_file(db):
    # frische Datei (10 s) = laufender Upload → nicht als Orphan melden
    audio = recovery.settings.AUDIO_DIR
    _touch(audio / "fresh.webm", age_s=10)
    with Session(db) as s:
        res = recovery.recovery_scan(_admin_req(), s)
    assert res["count"] == 0


def test_scan_requires_admin(db):
    audio = recovery.settings.AUDIO_DIR
    _touch(audio / "orphan.webm", age_s=3600)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recovery.recovery_scan(_nonadmin_req(), s)
        assert ei.value.status_code == 403


def test_restore_creates_visible_recording(db):
    audio = recovery.settings.AUDIO_DIR
    _touch(audio / "lost.webm", age_s=3600)
    with Session(db) as s:
        res = recovery.recovery_restore(
            recovery.RestoreBody(filename="lost.webm"), _admin_req(), s)
        assert res["original_name"].startswith("[wiederhergestellt]")
        rec = s.get(Recording, 1)
        assert rec is not None
        assert rec.status == "uploaded"
        assert rec.user_id is None  # anonym, aber sichtbar
        # Datei wurde kopiert, nicht die Waise selbst referenziert
        assert Path(rec.stored_path) != audio / "lost.webm"
        assert Path(rec.stored_path).is_file()
        # Waise existiert weiter (Sweep kann sie später räumen)
        assert (audio / "lost.webm").is_file()


def test_restore_rejects_traversal(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recovery.recovery_restore(
                recovery.RestoreBody(filename="../etc/passwd"), _admin_req(), s)
        assert ei.value.status_code == 400


def test_restore_rejects_referenced_file(db):
    audio = recovery.settings.AUDIO_DIR
    ref = audio / "inuse.wav"
    _touch(ref, age_s=3600)
    with Session(db) as s:
        s.add(Recording(id=1, uid="r1", original_name="in.wav",
                        stored_path=str(ref), user_id=1,
                        status="done", text="X"))
        s.commit()
        with pytest.raises(HTTPException) as ei:
            recovery.recovery_restore(
                recovery.RestoreBody(filename="inuse.wav"), _admin_req(), s)
        assert ei.value.status_code == 409


def test_restore_missing_file_404(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recovery.recovery_restore(
                recovery.RestoreBody(filename="nope.webm"), _admin_req(), s)
        assert ei.value.status_code == 404
