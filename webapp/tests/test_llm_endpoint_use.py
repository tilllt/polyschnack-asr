"""BYOK-Nutzung (Task E3) — Auswahl pro Transkription, Override in der Pipeline."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import crypto, llm
from app.models import Recording, User, UserLlmEndpoint
from app.routers import recordings


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


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
        s.add(User(id=1, sub="a", kind="oidc"))
        s.add(User(id=2, sub="b", kind="oidc"))
        s.add(UserLlmEndpoint(id=1, user_id=1, name="mistral",
                              base_url="https://api.mistral.ai/v1",
                              api_key=crypto.encrypt("sk-own"), model="mistral-small-latest"))
        s.add(UserLlmEndpoint(id=2, user_id=2, name="fremd",
                              base_url="https://api.openai.com/v1",
                              api_key=crypto.encrypt("sk-fremd"), model="gpt-4o-mini"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="uploaded"))
        s.commit()
    return eng


@pytest.fixture()
def qm(monkeypatch):
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)
    return calls


def _transcribe(session, uid, **kw):
    return recordings.transcribe_ep(
        "r1", _req(uid), enable_vad=False, enable_diarize=False,
        enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
        enable_punctuation=None, enable_llm_enhance=None,
        prompt_template_id=None, delivery_target_id=None,
        llm_endpoint_id=kw.get("llm_endpoint_id"), backend="", session=session)


def test_transcribe_sets_endpoint_flag(db, qm):
    with Session(db) as s:
        _transcribe(s, 1, llm_endpoint_id=1)
        rec = s.get(Recording, 1)
        assert rec.llm_endpoint_id == 1


def test_foreign_endpoint_403(db, qm):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            _transcribe(s, 1, llm_endpoint_id=2)
        assert ei.value.status_code == 403


def test_anon_with_endpoint_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            _transcribe(s, None, llm_endpoint_id=1)
        assert ei.value.status_code == 403


def test_chat_uses_endpoint_override(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        import httpx
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "Antwort"}}]
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.chat("System", "User", endpoint={
        "base_url": "https://byok.example.com/v1", "api_key": "sk-byok",
        "model": "own-model"})
    assert out == "Antwort"
    assert captured["url"] == "https://byok.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-byok"
    assert captured["json"]["model"] == "own-model"
    assert "sk-byok" not in str(captured["headers"]).replace("sk-byok", "")


def test_service_passes_user_credentials(db, monkeypatch):
    """process_recording: BYOK-Key wird entschlüsselt an llm.chat übergeben."""
    from pathlib import Path

    from app import llm as llm_mod
    from app import service as service_mod

    monkeypatch.setattr(service_mod, "engine", db)

    class _FakeClient:
        class _Caps:
            streaming = False

        capabilities = _Caps()

        def transcribe_async(self, audio_bytes, filename, mime, noise_reduce=True,
                             on_progress=None):
            return {"text": "Rohtext", "duration": 1.0, "language": "de",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "Rohtext"}]}

    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod.crud, "set_progress",
                        lambda session, rec_id, pct: None)
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    calls = {}
    def fake_chat(system, text, endpoint=None):
        calls["ep"] = endpoint
        return "OK"

    monkeypatch.setattr(llm_mod, "chat", fake_chat)

    def fake_update(session, rec_id, **kw):
        r = session.get(Recording, rec_id)
        if r is not None:
            r.status = kw.get("status", "done")
            r.text = kw.get("text") or r.text
            session.add(r)
            session.commit()

    monkeypatch.setattr(service_mod.crud, "update_result", fake_update)

    audio = Path(db.url.database).parent / "a.mp3"
    audio.write_bytes(b"MP3")
    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.prompt_template_id = None
        rec.llm_endpoint_id = 1
        rec.enable_llm_enhance = True
        rec.stored_path = str(audio)
        s.add(rec)
        s.commit()

    service_mod.process_recording(1, backend="pk-python")

    assert calls["ep"] == {"base_url": "https://api.mistral.ai/v1",
                           "api_key": "sk-own", "model": "mistral-small-latest"}
