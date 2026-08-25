"""Change 123 — Self-Healing: Einträge ohne uid + retranscribe-Härtung.

Befund (2026-08-25): Einträge mit uid NULL/leer (Migrations-Altlast,
Crash-Waise) erscheinen in der Liste mit uid:null — Retranscribe/Delete
rufen /api/recordings/null/... auf → get_recording_by_uid findet nichts →
404, der Eintrag ist unaufräumbar. Außerdem prüft retranscribe die
Audiodatei nicht (stiller Fail: enqueue → Worker failed ohne verwertbare
Meldung).
"""

import uuid

import pytest
from fastapi import HTTPException


def _mk_fake_request(user_id=1):
    class _FakeRequest:
        def __init__(self, session):
            self.session = session

    return _FakeRequest({"user_id": user_id})


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.config import settings

    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    return eng


@pytest.fixture(autouse=True)
def _patch_auth(db, monkeypatch):
    """Identität + Admin/Key-Checks mocken (Muster aus test_diarize_params)."""
    from app.routers import recordings

    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    monkeypatch.setattr(recordings, "_key_cap", lambda request, session=None: None)
    monkeypatch.setattr(recordings, "_is_admin_session", lambda request: False)
    monkeypatch.setattr(recordings, "_schedule_peaks", lambda *a, **k: None)


def test_repair_fuellt_uid_null_in_recording(tmp_path, monkeypatch):
    """Zeile mit uid NULL (per SQL) → Repair vergibt eindeutige hex-uid."""
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.models import Recording

    with Session(eng) as s:
        rec = Recording(
            uid=None,  # type: ignore[arg-type]  # Alt-Zeile ohne uid
            original_name="waise.mp3",
            stored_path="/nonexistent/waise.mp3",
            mime="audio/mpeg",
            size_bytes=1,
            status="failed",
        )
        s.add(rec)
        s.commit()
        rec_id = rec.id
    # Repair ausführen
    from app.db import _repair_missing_uids

    with Session(eng) as s:
        _repair_missing_uids(s)
    with Session(eng) as s:
        from sqlmodel import select

        r = s.exec(select(Recording).where(Recording.id == rec_id)).first()
        assert r is not None
        assert r.uid and len(r.uid) == 32  # uuid4-hex
        assert r.uid == r.uid.lower()
        # Eindeutigkeit: zweiter Lauf ändert nichts
        with Session(eng) as s2:
            _repair_missing_uids(s2)
        r2 = s.exec(select(Recording).where(Recording.id == rec_id)).first()
        assert r2.uid == r.uid


def test_repair_fuellt_uid_null_in_annotation(tmp_path, monkeypatch):
    """Auch Annotation-Zeilen ohne uid werden repariert."""
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.models import Annotation, Recording

    with Session(eng) as s:
        rec = Recording(
            uid=None, original_name="w.mp3", stored_path="/nonexistent/w.mp3",
            mime="audio/mpeg", size_bytes=1, status="failed")
        s.add(rec)
        s.flush()
        ann = Annotation(uid=None, rec_id=rec.id)  # type: ignore[arg-type]
        s.add(ann)
        s.commit()
        ann_id = ann.id
    from app.db import _repair_missing_uids

    with Session(eng) as s:
        _repair_missing_uids(s)
    with Session(eng) as s:
        from sqlmodel import select

        a = s.exec(select(Annotation).where(Annotation.id == ann_id)).first()
        assert a is not None
        assert a.uid and len(a.uid) == 32


def test_retranscribe_ohne_datei_gibt_410_statt_still_enqueue(db, monkeypatch):
    """Retranscribe auf Aufnahme ohne Datei → 410 (vorher 200 = stiller Fail)."""
    from sqlmodel import Session

    from app.models import Recording
    from app.routers import recordings

    # enqueue mocken (globales Singleton + wir erwarten, dass es NICHT läuft)
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)

    with Session(db) as s:
        s.add(Recording(id=1, uid="r1", original_name="waise.mp3",
                        stored_path="/nonexistent/waise.mp3",
                        mime="audio/mpeg", size_bytes=1, status="failed",
                        user_id=1, owner_user_id=1))
        s.commit()
    with Session(db) as s:
        with pytest.raises(HTTPException) as exc:
            recordings.retranscribe("r1", request=_mk_fake_request(1), session=s)
        assert exc.value.status_code == 410
    assert calls == [], "retranscribe darf ohne Datei nicht enqueuen"


def test_delete_ohne_datei_funktioniert(db):
    """Delete auf Aufnahme ohne Datei MUSS gehen (Waisen aufräumbar)."""
    from sqlmodel import Session

    from app.models import Recording
    from app.routers import recordings

    with Session(db) as s:
        s.add(Recording(id=1, uid="r1", original_name="waise.mp3",
                        stored_path="/nonexistent/waise.mp3",
                        mime="audio/mpeg", size_bytes=1, status="failed",
                        user_id=1, owner_user_id=1))
        s.commit()
    with Session(db) as s:
        resp = recordings.delete_recording_endpoint("r1", request=_mk_fake_request(1), session=s)
        assert resp is not None
        assert s.get(Recording, 1) is None
