"""Change 121: transcribe überschreibt Upload-Settings nicht mehr still.

Befund (2026-08-25): POST /recordings/{rid}/transcribe setzte die
Run-Settings BEDINGUNGSLOS auf seine Form-Defaults (enable_vad=False,
vad_mode="off", enable_diarize=False, ...). Ein Client, der nach dem
Upload nur transcribe aufruft (ohne die Settings-Felder zu wiederholen),
verlor still seine Upload-Auswahl. Jetzt: fehlende Felder (None) behalten
den queued-Run-Wert; explizit gesendete Felder gewinnen weiterhin.
"""

import io
import wave

import pytest


def _wav_bytes(duration_s: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(duration_s * 16000))
    return buf.getvalue()


def _setup(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.config import settings

    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    # QueueManager ist ein globales Singleton — enqueue mocken, damit die
    # Tests nicht über rec_id kollidieren (Job-Registry überlebt die Tests).
    from app.routers import recordings

    monkeypatch.setattr(recordings.queue_manager, "enqueue", lambda *a, **k: 1)
    return eng


def _run_row(eng):
    from sqlmodel import Session, select

    from app.models import TranscriptionRun

    with Session(eng) as s:
        return s.exec(select(TranscriptionRun).order_by(TranscriptionRun.id.asc())).first()


def test_transcribe_ohne_felder_behaelt_upload_settings(tmp_path, monkeypatch):
    """Upload mit VAD+Diarize → transcribe ohne Form-Felder → Settings bleiben."""
    eng = _setup(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/recordings",
                   files={"file": ("v.wav", _wav_bytes(), "audio/wav")},
                   data={"name": "v.wav", "enable_vad": "true",
                         "enable_diarize": "true"})
        assert r.status_code == 201, r.text
        rid = r.json()["uid"]
        # KEINE Settings-Felder im transcribe-Call — wie ein schlanker API-Client
        r2 = c.post(f"/api/recordings/{rid}/transcribe")
        assert r2.status_code == 200, r2.text
    run = _run_row(eng)
    assert run is not None
    assert run.enable_vad is True, "Upload-Setting enable_vad ging still verloren"
    assert run.vad_mode == "edges"
    assert run.enable_diarize is True, "Upload-Setting enable_diarize ging still verloren"


def test_transcribe_explizite_felder_gewinnen(tmp_path, monkeypatch):
    """Explizit gesendete Felder überschreiben weiterhin (Browser-Verhalten)."""
    eng = _setup(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/recordings",
                   files={"file": ("v.wav", _wav_bytes(), "audio/wav")},
                   data={"name": "v.wav", "enable_vad": "true"})
        assert r.status_code == 201, r.text
        rid = r.json()["uid"]
        # Browser sendet alles immer mit — jetzt explizit VAD aus
        r2 = c.post(f"/api/recordings/{rid}/transcribe",
                    data={"enable_vad": "false", "vad_mode": "off"})
        assert r2.status_code == 200, r2.text
    run = _run_row(eng)
    assert run is not None
    assert run.enable_vad is False
    assert run.vad_mode == "off"


def test_transcribe_ohne_queued_run_nutzt_defaults(tmp_path, monkeypatch):
    """Kein queued-Run (Upload-Run schon abgearbeitet) → neuer Run mit Defaults."""
    eng = _setup(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/recordings",
                   files={"file": ("v.wav", _wav_bytes(), "audio/wav")},
                   data={"name": "v.wav"})
        assert r.status_code == 201, r.text
        rid = r.json()["uid"]
        # Upload-Run künstlich abschließen → kein queued-Run mehr
        run = _run_row(eng)
        from sqlmodel import Session

        with Session(eng) as s:
            run.status = "done"
            s.add(run)
            s.commit()
        r2 = c.post(f"/api/recordings/{rid}/transcribe")
        assert r2.status_code == 200, r2.text
    from sqlmodel import Session, select

    from app.models import TranscriptionRun

    with Session(eng) as s:
        runs = s.exec(select(TranscriptionRun).order_by(TranscriptionRun.id.asc())).all()
        assert len(runs) == 2  # Upload-Run (done) + neuer transcribe-Run
        new_run = runs[1]
        assert new_run.enable_vad is False
        assert new_run.vad_mode == "off"
        assert new_run.enable_diarize is False
        assert new_run.enable_noise_reduce is True  # bisheriger Modell-Default
