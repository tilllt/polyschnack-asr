"""Opt-in-Toggles (Task A12/A13): Defaults aus, nichts automatisch, paid-Sperre."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Recording, User
from app.routers import recordings
from app.service import run_llm_enhance, run_punctuation


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
        s.add(User(id=1, sub="oidc-user"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="uploaded"))
        s.add(Recording(id=2, uid="r2", original_name="b.mp3", stored_path="p",
                        user_id=None, status="uploaded"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


@pytest.fixture()
def qm(monkeypatch):
    """Gemockte Queue, damit enqueue keine echte DB/Threads braucht."""
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)
    return calls


def test_stubs_pass_through():
    assert run_punctuation("Hallo welt", "local") == "Hallo welt"
    t, segs = run_llm_enhance("Hallo", [{"text": "Hallo"}])
    assert t == "Hallo" and segs == [{"text": "Hallo"}]


def test_anon_llm_enhance_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings.settings, "POLYSCHNACK_DEFAULT_LLM_ENHANCE", False)
    # Zugriff isolieren: hier zählt nur der paid-Check (ensure_access ist in A4 getestet)
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r2", _req(None), enable_vad=False, enable_diarize=False,
                diarize_num_speakers=None, diarize_min_duration_off=None,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=None, enable_llm_enhance=True,
                prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert ei.value.status_code == 403
    assert not qm


def test_anon_llm_punctuation_mode_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings.settings, "POLYSCHNACK_PUNCTUATION_MODE", "llm")
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r2", _req(None), enable_vad=False, enable_diarize=False,
                diarize_num_speakers=None, diarize_min_duration_off=None,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=True, enable_llm_enhance=None,
                prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert ei.value.status_code == 403
    assert not qm


def test_anon_local_punctuation_ok(db, qm, monkeypatch):
    monkeypatch.setattr(recordings.settings, "POLYSCHNACK_PUNCTUATION_MODE", "off")
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        r = recordings.transcribe_ep(
            "r2", _req(None), enable_vad=False, enable_diarize=False,
            diarize_num_speakers=None, diarize_min_duration_off=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=True, enable_llm_enhance=None,
            prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert r["status"] == "queued"
    assert len(qm) == 1


def test_oidc_llm_enhance_ok(db, qm):
    with Session(db) as s:
        r = recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=False,
            diarize_num_speakers=None, diarize_min_duration_off=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=True,
            prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert r["status"] == "queued"
        rec = s.get(Recording, 1)
        assert rec.enable_llm_enhance is True
    assert len(qm) == 1


def test_retranscribe_sets_toggle_flags(db, qm):
    with Session(db) as s:
        params = recordings.RetranscribeParams(
            enable_punctuation=True, enable_llm_enhance=False)
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        assert rec.enable_punctuation is True
        assert rec.enable_llm_enhance is False


def test_retranscribe_speichert_diarize_params(db, qm):
    """Diarization-Tuning (Punkte 1+2) wird am Recording gespeichert."""
    with Session(db) as s:
        params = recordings.RetranscribeParams(
            enable_diarize=True,
            diarize_num_speakers=2,
            diarize_min_duration_off=0.4,
        )
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        assert rec.enable_diarize is True
        assert rec.diarize_num_speakers == 2
        assert rec.diarize_min_duration_off == 0.4


def test_retranscribe_diarize_params_default_none(db, qm):
    """Ohne Angabe bleiben die Tuning-Werte None (Pipeline-Default)."""
    with Session(db) as s:
        recordings.retranscribe("r1", recordings.RetranscribeParams(enable_diarize=True), _req(1), s)
        rec = s.get(Recording, 1)
        assert rec.diarize_num_speakers is None
        assert rec.diarize_min_duration_off is None


def test_defaults_are_off():
    assert settings.POLYSCHNACK_DEFAULT_PUNCTUATION is False
    assert settings.POLYSCHNACK_DEFAULT_LLM_ENHANCE is False
    assert settings.POLYSCHNACK_PUNCTUATION_MODE == "off"
