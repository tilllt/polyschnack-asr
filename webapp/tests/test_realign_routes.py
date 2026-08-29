"""Change 113 Regressionstests: Re-Align übernimmt separate_backend (BGM-Removal).

User-Befund 24.08.: „Wenn man Re-align drückt, kann man nicht die bgm Removal
auswählen." — die realign-Route ignorierte separate_backend und
_schedule_realign lief immer auf dem Original-Audio (bei Musik-Aufnahmen
alignment=skipped). Fix: Form-Feld + Durchreichung + Separation in der
Align-Kette (wie Transkriptions-Pipeline, ehrlicher Fallback Original).
"""

import io
import wave
from pathlib import Path

import pytest
from fastapi import Form


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine
    from app.models import Recording, User
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    # service.py bindet `engine` beim Import (`from .db import engine`) —
    # _schedule_realign öffnet Session(engine) direkt → beide Pfade mocken.
    monkeypatch.setattr("app.db.engine", eng)
    monkeypatch.setattr("app.service.engine", eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="oidc-user"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"RIFF....")
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1, status="uploaded"))
        s.commit()
    return eng


class _FakeUser:
    id = 1
    key_level = "full"


class _FakeIdentity:
    user = _FakeUser()
    key_level = "full"


@pytest.fixture()
def _patch_identity(monkeypatch):
    from app import identity
    monkeypatch.setattr(identity, "current_identity",
                        lambda request, session=None: _FakeIdentity())


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def _make_done(db):
    from sqlmodel import Session
    from app.models import Recording
    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.status = "done"
        s.add(rec)
        s.commit()


def _patch_schedule(monkeypatch):
    """_schedule_realign mocken und Aufrufe sammeln.

    Die Route importiert `_schedule_realign` funktionslokal aus app.service
    (`from ..service import ...`) → das Mock muss dort sitzen.
    """
    calls = {}

    def fake_schedule(rec_id, separate_backend="none"):
        calls["rec_id"] = rec_id
        calls["separate_backend"] = separate_backend
        return True

    monkeypatch.setattr("app.service._schedule_realign", fake_schedule)
    return calls


# ---------------------------------------------------------------- Route ---

def test_realign_reicht_separate_backend_durch(db, _patch_identity, monkeypatch):
    """Re-Align mit separate_backend=htdemucs → _schedule_realign bekommt das Feld."""
    from sqlmodel import Session
    from app.routers import segments
    calls = _patch_schedule(monkeypatch)
    _make_done(db)
    with Session(db) as s:
        res = segments.realign_recording("r1", _req(1), "htdemucs", s)
    assert res["alignment"] == "pending"
    assert calls["separate_backend"] == "htdemucs"


def test_realign_default_none(db, _patch_identity, monkeypatch):
    """Re-Align ohne separate_backend → 'none' (kein Drift, Aligner wie bisher)."""
    from sqlmodel import Session
    from app.routers import segments
    calls = _patch_schedule(monkeypatch)
    _make_done(db)
    with Session(db) as s:
        res = segments.realign_recording("r1", _req(1), "none", s)
    assert res["alignment"] == "pending"
    assert calls["separate_backend"] == "none"


def test_realign_guard_bei_form_objekt(db, _patch_identity, monkeypatch):
    """Direkte Funktionsaufrufe (Tests) liefern Form(...)-Objekte → Guard setzt 'none'."""
    from sqlmodel import Session
    from app.routers import segments
    calls = _patch_schedule(monkeypatch)
    _make_done(db)
    with Session(db) as s:
        res = segments.realign_recording("r1", _req(1), Form("htdemucs"), s)
    assert res["alignment"] == "pending"
    assert calls["separate_backend"] == "none"


# --------------------------------------------------------------- Service ---

def test_schedule_realign_separiert_audio(db, monkeypatch, tmp_path):
    """_schedule_realign mit separate_backend → vocals landen im Alignment-Cache."""
    import app.service as service

    # Audio-Datei mit echtem Inhalt (Stored-Path zeigt darauf)
    audio = tmp_path / "real.wav"
    audio.write_bytes(b"ORIGINAL-AUDIO-BYTES")
    from sqlmodel import Session
    from app.models import Recording
    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.status = "done"
        rec.stored_path = str(audio)
        s.add(rec)
        s.commit()

    monkeypatch.setattr("app.aligner_client.ALIGN_WORDS_ENABLED", True)

    # SeparateClient mocken: erreichbar, liefert vocals
    class _FakeSep:
        def __init__(self):
            self.backend = None

        def health(self):
            return True

        def separate(self, audio_bytes, backend="htdemucs"):
            self.backend = backend
            return b"VOCALS-VOCALS"

    fake_sep = _FakeSep()
    monkeypatch.setattr("app.separate_client.SeparateClient", lambda: fake_sep)

    # Change 155 (Schritt 4): die separate-Logik läuft jetzt im Worker
    # (_prepare_align_audio) — vocals sind die Align-Eingabe.
    prepared = service._prepare_align_audio(1, separate_backend="htdemucs")
    assert prepared is not None
    assert fake_sep.backend == "htdemucs"
    assert prepared[0] == b"VOCALS-VOCALS"
    assert prepared[1] is None  # Change 114: vad_mode off → kein Trim

    # _schedule_realign enqueued einen align-Queue-Job (kein nackter Thread).
    enqueued = {}

    class _FakeQueue:
        def enqueue(self, rec_id, user_id=None, backend=None, priority=0,
                    kind="transcribe", payload=None, key=None):
            enqueued.update(rec_id=rec_id, kind=kind, key=key, payload=payload)
            return 1

    monkeypatch.setattr("app.queue.queue_manager", _FakeQueue())
    ok = service._schedule_realign(1, separate_backend="htdemucs")
    assert ok is True
    assert enqueued["rec_id"] == 1 and enqueued["kind"] == "align"
    assert enqueued["key"] == "align-1"
    assert enqueued["payload"] == {"separate_backend": "htdemucs"}
    with Session(db) as s:
        assert s.get(Recording, 1).alignment == "pending"


def test_schedule_realign_fallback_bei_sep_fehler(db, monkeypatch, tmp_path):
    """crispr-sep nicht erreichbar → ehrlicher Fallback: Original als Align-Eingabe."""
    import app.service as service
    audio = tmp_path / "real.wav"
    audio.write_bytes(b"ORIGINAL-AUDIO-BYTES")
    from sqlmodel import Session
    from app.models import Recording
    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.status = "done"
        rec.stored_path = str(audio)
        s.add(rec)
        s.commit()

    monkeypatch.setattr("app.aligner_client.ALIGN_WORDS_ENABLED", True)

    class _DownSep:
        def health(self):
            return False

    monkeypatch.setattr("app.separate_client.SeparateClient", lambda: _DownSep())

    prepared = service._prepare_align_audio(1, separate_backend="htdemucs")
    assert prepared is not None
    assert prepared[0] == b"ORIGINAL-AUDIO-BYTES"  # Fallback, kein Abbruch
