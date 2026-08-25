"""Change 124 — Cancel für Background-Alignment + Diarization-Nachprüfung.

Befunde (2026-08-25):
- _run_background_align läuft nach „done" mit job=None → _cancelled(None,…)
  → False: der Worker ist immun gegen Cancel; der Cancel-Endpoint findet
  keinen Queue-Job („no active job") und das Frontend zeigt den Button bei
  done gar nicht.
- Diarization: blockierender Call; _cancelled wird nur VOR der Phase geprüft
  — ein Cancel während des Calls greift erst nach dem Save.
"""

from types import SimpleNamespace

import pytest

from app.queue import Job


class _FakeJob:
    def __init__(self, cancel: bool = False, max_s: float = 3600.0):
        self.cancel_requested = cancel
        self._max_processing_s = max_s
        import time
        self.started_at = time.time()

    @property
    def running_s(self) -> float:
        import time
        return time.time() - self.started_at


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
    # QueueManager-Singleton + Identität für den Cancel-Endpoint mocken
    from app.routers import cancel as cancel_router

    monkeypatch.setattr(cancel_router, "_current_user",
                        lambda request, session=None: 1)
    monkeypatch.setattr(cancel_router, "_key_cap",
                        lambda request, session=None: None)
    monkeypatch.setattr("app.identity.current_identity",
                        lambda request, session: SimpleNamespace(
                            user=SimpleNamespace(is_admin=False)))
    monkeypatch.setattr(cancel_router.queue_manager, "cancel",
                        lambda *a, **k: False)
    return eng


@pytest.fixture(autouse=True)
def _clean_bg_cancel_set():
    """Test-Isolation: Cancel-Set nach jedem Test leeren."""
    from app import service
    yield
    with service._align_lock:
        service._BG_ALIGN_CANCEL.clear()


def test_response_enthaelt_diar_status():
    """Change 128: Recording-Response liefert diar_status (für den
    Cancel-Button bei laufender Rediarize)."""
    from app.models import Recording
    from app.routers.recordings import _recording_to_dict

    rec = Recording(
        uid="x", original_name="a.mp3", title="a",
        duration_s=10.0, size_bytes=100, diar_status="running",
    )
    d = _recording_to_dict(rec)
    assert d["diar_status"] == "running"

    rec2 = Recording(uid="y", original_name="b.mp3", title="b",
                     duration_s=1.0, size_bytes=1)
    assert _recording_to_dict(rec2)["diar_status"] == "done"


def test_response_eta_bei_laufender_rediarize():
    """Change 127: done + diar_status running → ETA wird geliefert
    (Rediarize-ETA, Basis phase_started_at) statt immer None."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.models import Recording
    from app.routers.recordings import _recording_to_dict

    rec = Recording(
        uid="x", original_name="a.mp3", title="a",
        duration_s=600.0, size_bytes=100,
        status="done", diar_status="running",
        phase_started_at=datetime.now(timezone.utc) - timedelta(seconds=60),
    )
    run = SimpleNamespace(
        diarize_num_speakers=None, diarize_min_duration_off=None,
        diarize_method="pyannote", enable_streaming=False,
        enable_noise_reduce=False, enable_enhance="off",
        enable_punctuation=False, enable_vad=False, enable_diarize=True,
    )
    d = _recording_to_dict(rec, run=run)
    assert d["eta_low_s"] is not None and d["eta_high_s"] is not None
    # 600 s × 0.65 = 390 s erwartet, 60 s elapsed → Rest ~330 s (Fallback ±50 %)
    assert d["eta_high_s"] >= d["eta_low_s"] > 0


def test_response_eta_bei_laufendem_background_align():
    """Change 127: done + alignment running → Align-ETA (Basis
    phase_started_at), analog zur Rediarize-ETA."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.models import Recording
    from app.routers.recordings import _recording_to_dict

    rec = Recording(
        uid="x", original_name="a.mp3", title="a",
        duration_s=600.0, size_bytes=100,
        status="done", alignment="running",
        phase_started_at=datetime.now(timezone.utc) - timedelta(seconds=60),
    )
    run = SimpleNamespace(
        diarize_num_speakers=None, diarize_min_duration_off=None,
        diarize_method="pyannote", enable_streaming=False,
        enable_noise_reduce=False, enable_enhance="off",
        enable_punctuation=False, enable_vad=False, enable_diarize=True,
    )
    d = _recording_to_dict(rec, run=run)
    assert d["eta_low_s"] is not None and d["eta_high_s"] is not None
    assert d["eta_high_s"] >= d["eta_low_s"] > 0



def test_cancel_endpoint_erkennt_background_alignment(tmp_path, monkeypatch):
    """Cancel bei alignment=running → cancelled=true + rec_id im Cancel-Set."""
    eng = _setup(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app import service
    from app.main import app
    from app.models import Recording

    with TestClient(app) as c:
        # Recording NACH dem App-Start anlegen — die Boot-Recovery (lifespan)
        # würde alignment=running sonst als „hängend" auf skipped setzen.
        with Session(eng) as s:
            s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                            stored_path="/tmp/a.mp3", mime="audio/mpeg",
                            size_bytes=1, status="done", alignment="running",
                            user_id=1, owner_user_id=1))
            s.commit()
        resp = c.post("/api/recordings/r1/cancel")
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled"] is True
        assert resp.json()["status"] == "cancelled"
    with service._align_lock:
        assert 1 in service._BG_ALIGN_CANCEL


def test_cancel_endpoint_alignment_pending_ohne_queue(tmp_path, monkeypatch):
    """Cancel bei alignment=pending (kein Queue-Job) → ebenfalls cancelled."""
    eng = _setup(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app import service
    from app.main import app
    from app.models import Recording

    with TestClient(app) as c:
        with Session(eng) as s:
            s.add(Recording(id=2, uid="r2", original_name="a.mp3",
                            stored_path="/tmp/a.mp3", mime="audio/mpeg",
                            size_bytes=1, status="done", alignment="pending",
                            user_id=1, owner_user_id=1))
            s.commit()
        resp = c.post("/api/recordings/r2/cancel")
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled"] is True
    with service._align_lock:
        assert 2 in service._BG_ALIGN_CANCEL


def test_run_align_phase_bg_abbruch_ohne_align_call(tmp_path, monkeypatch):
    """BG-Align mit rec_id im Cancel-Set → kein align()-Call, Segmente unverändert."""
    _setup(tmp_path, monkeypatch)
    from app import service

    with service._align_lock:
        service._BG_ALIGN_CANCEL.add(1)

    called = []

    class _FakeClient:
        def health(self):
            return True

        def align(self, *a, **k):
            called.append(a)
            return [{"word": "x", "start": 0.0, "end": 0.1}]

    monkeypatch.setattr("app.aligner_client.AlignerClient", lambda: _FakeClient())

    segs = [{"start": 0.0, "end": 2.0, "text": "Hallo Welt",
             "words": [{"word": "Hallo", "start": 0.0, "end": 0.4}]}]
    result = service._run_align_phase(
        1, segs, b"audio-bytes", "rec.wav", "de", job=None, background=True)
    assert result == segs, "Segmente müssen unverändert bleiben"
    assert called == [], "align() darf bei Cancel nicht aufgerufen werden"


def test_abort_if_cancelled_diar_nachpruefung(tmp_path, monkeypatch):
    """Helper: Cancel nach der Diar-Phase → failed + Meldung; ohne Cancel → False."""
    eng = _setup(tmp_path, monkeypatch)
    from sqlmodel import Session, select

    from app import service
    from app.models import Recording

    # service importiert `from .db import engine` zur Ladezeit — eigener
    # Referenzpunkt; für _abort_recording auch hier mocken.
    monkeypatch.setattr(service, "engine", eng)

    with Session(eng) as s:
        s.add(Recording(id=3, uid="r3", original_name="a.mp3",
                        stored_path="/tmp/a.mp3", mime="audio/mpeg",
                        size_bytes=1, status="processing", user_id=1,
                        owner_user_id=1))
        s.commit()

    job = _FakeJob(cancel=True)
    assert service._abort_if_cancelled(job, 3) is True
    with Session(eng) as s:
        r = s.exec(select(Recording).where(Recording.id == 3)).first()
        assert r.status == "failed"
        assert "Abgebrochen" in (r.error or "")

    job2 = _FakeJob(cancel=False)
    assert service._abort_if_cancelled(job2, 3) is False
