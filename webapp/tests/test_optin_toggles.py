"""Opt-in-Toggles (Task A12/A13): Defaults aus, nichts automatisch, paid-Sperre."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Recording, TranscriptionRun, User
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
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"RIFF....")  # Change 023: transcribe_ep verlangt echte Datei
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1, status="uploaded"))
        s.add(Recording(id=2, uid="r2", original_name="b.mp3", stored_path=str(audio),
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


def test_punctuation_off_and_unknown_modes_pass_through():
    assert run_punctuation("hallo welt", "off") == "hallo welt"
    assert run_punctuation("hallo welt", "") == "hallo welt"
    assert run_punctuation("hallo welt", "bogus") == "hallo welt"


def test_punctuation_llm_mode_calls_endpoint(monkeypatch):
    """llm-Modus ruft llm.chat und übernimmt das Ergebnis."""
    calls = {}

    def fake_chat(system, user_text, max_tokens=2000, endpoint=None):
        calls["system"] = system
        calls["user"] = user_text
        return "Hallo, Welt!"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    out = run_punctuation("hallo welt", "llm")
    assert out == "Hallo, Welt!"
    assert "Satzzeichen" in calls["system"]


def test_punctuation_llm_mode_error_passthrough(monkeypatch):
    """LLM-Fehler (kein Endpunkt) → Text unverändert, kein Crash."""
    def boom(system, user_text, max_tokens=2000, endpoint=None):
        raise RuntimeError("LLM-Endpunkt nicht konfiguriert")

    monkeypatch.setattr("app.llm.chat", boom)
    assert run_punctuation("hallo welt", "llm") == "hallo welt"


def test_llm_enhance_redistributes_words_proportionally(monkeypatch):
    """Enhance verteilt den korrigierten Text proportional auf Segmente —
    Wörter/Segment-Verhältnis bleibt, Timestamps unangetastet."""
    def fake_chat(system, user_text, max_tokens=2000, endpoint=None):
        return "Hallo korrigierter Welttext der verteilt wird"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    segs = [
        {"start": 0.0, "end": 1.0, "text": "hallo welt", "words": [{"word": "hallo"}]},
        {"start": 1.0, "end": 2.0, "text": "test", "words": [{"word": "test"}]},
    ]
    text, out = run_llm_enhance("hallo welt test", segs)
    # 6 neue Wörter, alte Verteilung 2:1 → ~4:2
    assert len(out) == 2
    assert out[0]["start"] == 0.0 and out[0]["end"] == 1.0  # Timestamps intakt
    assert out[1]["start"] == 1.0 and out[1]["end"] == 2.0
    assert len(out[0]["text"].split()) >= len(out[1]["text"].split())
    # Gesamttext = Konkatenation der Segment-Texte
    assert text == " ".join(s["text"] for s in out)


def test_llm_enhance_error_passthrough(monkeypatch):
    """LLM-Fehler → unverändert, kein Crash."""
    def boom(system, user_text, max_tokens=2000, endpoint=None):
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.llm.chat", boom)
    segs = [{"text": "hallo"}]
    t, s = run_llm_enhance("hallo", segs)
    assert t == "hallo" and s == segs


def test_anon_llm_enhance_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings.settings, "POLYSCHNACK_DEFAULT_LLM_ENHANCE", False)
    # Zugriff isolieren: hier zählt nur der paid-Check (ensure_access ist in A4 getestet)
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r2", _req(None), enable_vad=False, enable_diarize=False,
                diarize_num_speakers=None, diarize_min_duration_off=None,
                diarize_method=None,
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
                diarize_method=None,
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
            diarize_method=None,
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
            diarize_method=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=True,
            prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert r["status"] == "queued"
        rec = s.get(Recording, 1)
        # Change 099: Settings liegen im Run (versionierte Wahrheit)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.enable_llm_enhance is True
    assert len(qm) == 1


def test_retranscribe_sets_toggle_flags(db, qm):
    with Session(db) as s:
        params = recordings.RetranscribeParams(
            enable_punctuation=True, enable_llm_enhance=False)
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        # Change 099: retranscribe legt einen NEUEN Run an
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.enable_punctuation is True
        assert run.enable_llm_enhance is False


def test_retranscribe_speichert_diarize_params(db, qm):
    """Diarization-Tuning (Punkte 1+2) wird im Run gespeichert (Change 099)."""
    with Session(db) as s:
        params = recordings.RetranscribeParams(
            enable_diarize=True,
            diarize_num_speakers=2,
            diarize_min_duration_off=0.4,
            diarize_method="foxnose",
        )
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.enable_diarize is True
        assert run.diarize_num_speakers == 2
        assert run.diarize_min_duration_off == 0.4
        # Bugfix 2026-08-15: Methode wurde vorher nie persistiert (stiller
        # Fallback auf Server-Default) — Regressionstest.
        assert run.diarize_method == "foxnose"


def test_retranscribe_diarize_params_default_none(db, qm):
    """Ohne Angabe bleiben die Tuning-Werte None (Pipeline-Default)."""
    with Session(db) as s:
        recordings.retranscribe("r1", recordings.RetranscribeParams(enable_diarize=True), _req(1), s)
        rec = s.get(Recording, 1)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.diarize_num_speakers is None
        assert run.diarize_min_duration_off is None


def test_defaults_are_off():
    assert settings.POLYSCHNACK_DEFAULT_PUNCTUATION is False
    assert settings.POLYSCHNACK_DEFAULT_LLM_ENHANCE is False
    assert settings.POLYSCHNACK_PUNCTUATION_MODE == "off"
