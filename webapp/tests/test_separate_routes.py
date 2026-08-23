"""Change 106 Regressionstests: separate_backend wird von ALLEN Routen
übernommen, die queued-Runs erzeugen (Fix 23.08. — Routen ignorierten das Feld,
Separation lief nie; Produktions-Befund: saisoncouplet-Re-Align ohne Änderung)."""

import io
import tempfile
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from app import db as db_module
    from app.main import app
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.config import settings
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def _patch_user(monkeypatch):
    from app.routers import recordings
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    from sqlmodel import Session, SQLModel, create_engine
    from app.models import Recording, User
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="oidc-user"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"RIFF....")
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1, status="uploaded"))
        s.commit()
    return eng


@pytest.fixture()
def qm(monkeypatch):
    from app.routers import recordings
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)
    return calls


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def _wav_bytes(duration_s: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(duration_s * 16000))
    return buf.getvalue()


def _first_run(tmp_path: Path):
    from sqlmodel import Session, select
    from app.models import TranscriptionRun
    import app.db as _db
    with Session(_db.engine) as s:
        return s.exec(select(TranscriptionRun).order_by(TranscriptionRun.id.asc())).first()

def test_upload_speichert_separate_backend(client, tmp_path):
    """Upload mit separate_backend=htdemucs → queued-Run trägt das Feld (Fix 23.08.)."""
    r = client.post(
        "/api/recordings",
        files={"file": ("sep.wav", _wav_bytes(), "audio/wav")},
        data={"name": "sep.wav", "separate_backend": "htdemucs"},
    )
    assert r.status_code == 201, r.text
    run = _first_run(tmp_path)
    assert run is not None
    assert run.separate_backend == "htdemucs"


def test_upload_separate_default_none(client, tmp_path):
    """Ohne Angabe bleibt separate_backend 'none' (Pipeline-Default)."""
    r = client.post(
        "/api/recordings",
        files={"file": ("plain.wav", _wav_bytes(), "audio/wav")},
        data={"name": "plain.wav"},
    )
    assert r.status_code == 201, r.text
    run = _first_run(tmp_path)
    assert run is not None
    assert run.separate_backend == "none"


def test_retranscribe_speichert_separate_backend(db, qm, _patch_user):
    """Retranscribe mit separate_backend → neuer Run trägt das Feld (Fix 23.08.)."""
    from sqlmodel import Session
    from app.models import Recording, TranscriptionRun
    from app.routers import recordings

    with Session(db) as s:
        params = recordings.RetranscribeParams(separate_backend="mel-band-roformer")
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.separate_backend == "mel-band-roformer"


def test_retranscribe_separate_default_none(db, qm, _patch_user):
    """Retranscribe ohne separate_backend → 'none' (kein Drift auf Alt-Runs)."""
    from sqlmodel import Session
    from app.models import Recording, TranscriptionRun
    from app.routers import recordings

    with Session(db) as s:
        recordings.retranscribe("r1", recordings.RetranscribeParams(), _req(1), s)
        rec = s.get(Recording, 1)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.separate_backend == "none"
