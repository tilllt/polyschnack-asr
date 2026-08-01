"""Post-Processing & Delivery-Pipeline (Task D4)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import service
from app.models import DeliveryTarget, PromptTemplate, Recording, User
from app.routers import recordings
from app.versions import list_versions


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
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3")
    with Session(eng) as s:
        s.add(User(id=1, sub="a", kind="oidc"))
        s.add(User(id=2, sub="b", kind="oidc"))
        s.add(PromptTemplate(id=1, user_id=1, name="meeting",
                             prompt="Fasse zusammen"))
        s.add(PromptTemplate(id=2, user_id=2, name="fremd", prompt="x"))
        s.add(DeliveryTarget(id=1, user_id=1, name="mail", kind="email",
                             config='{"to": "x@y.de"}'))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="uploaded"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


@pytest.fixture()
def qm(monkeypatch):
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)
    return calls


def test_transcribe_with_own_template_sets_flag(db, qm):
    with Session(db) as s:
        recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=False,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=1, delivery_target_id=None, backend="", session=s)
        rec = s.get(Recording, 1)
        assert rec.prompt_template_id == 1


def test_transcribe_foreign_template_403(db, qm):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r1", _req(1), enable_vad=False, enable_diarize=False,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=None, enable_llm_enhance=None,
                prompt_template_id=2, delivery_target_id=None, backend="", session=s)
        assert ei.value.status_code == 403


def test_anon_with_template_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r1", _req(None), enable_vad=False, enable_diarize=False,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=None, enable_llm_enhance=None,
                prompt_template_id=1, delivery_target_id=None, backend="", session=s)
        assert ei.value.status_code == 403


def test_transcribe_with_target_sets_pending(db, qm):
    with Session(db) as s:
        recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=False,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=None, delivery_target_id=1, backend="", session=s)
        rec = s.get(Recording, 1)
        assert rec.delivery_target_id == 1
        assert rec.delivery_status == "pending"


class _FakeClient:
    class _Caps:
        streaming = False

    capabilities = _Caps()

    def transcribe_async(self, audio_bytes, filename, mime, noise_reduce=True,
                         on_progress=None):
        return {"text": "Rohtext", "duration": 1.0, "language": "de",
                "segments": [{"start": 0.0, "end": 1.0, "text": "Rohtext"}]}


def test_service_runs_template_and_delivers(db, monkeypatch):
    """process_recording: Template → llm.chat ersetzt Text + postprocess-Version;
    Target → deliver() mit Status done."""
    from app import llm, service as service_mod
    from app import queue as queue_mod

    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(queue_mod.crud, "get_recording",
                        lambda s, rid: s.get(Recording, rid))
    from app import crud

    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod.crud, "update_result",
                        lambda session, rec_id, **kw: None)
    monkeypatch.setattr(service_mod.crud, "set_progress",
                        lambda session, rec_id, pct: None)
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)
    calls = {}
    monkeypatch.setattr(llm, "chat", lambda system, text: "Zusammenfassung: ...")
    from app import deliver as deliver_mod

    delivered = []
    monkeypatch.setattr(deliver_mod, "deliver",
                        lambda rec, target: delivered.append(rec.id))

    # Recording mit Template + Target
    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.prompt_template_id = 1
        rec.delivery_target_id = 1
        rec.delivery_status = "pending"
        s.add(rec)
        s.commit()

    service_mod.process_recording(1, backend="pk-python")

    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.delivery_status == "done"
        assert delivered == [1]
        kinds = [v.kind for v in list_versions(s, 1)]
        assert "transcribe" in kinds and "postprocess" in kinds


def test_service_delivery_failure_marks_failed(db, monkeypatch):
    from app import service as service_mod
    from app import queue as queue_mod

    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(queue_mod.crud, "get_recording",
                        lambda s, rid: s.get(Recording, rid))
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod.crud, "update_result",
                        lambda session, rec_id, **kw: None)
    monkeypatch.setattr(service_mod.crud, "set_progress",
                        lambda session, rec_id, pct: None)
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)
    from app import deliver as deliver_mod

    def boom(rec, target):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr(deliver_mod, "deliver", boom)

    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.delivery_target_id = 1
        rec.delivery_status = "pending"
        s.add(rec)
        s.commit()

    service_mod.process_recording(1, backend="pk-python")

    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.delivery_status == "failed"
        assert "SMTP down" in (rec.delivery_error or "")
