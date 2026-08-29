"""Change 057 — Re-Diarize: Endpunkt + Worker (Sprecher-Zuordnung).

Deckt ab:
- Route: Auth, 409 (nicht done / läuft bereits), 503 (Audio fehlt), 200
- _schedule_rediarize: Voraussetzungen, diar_status=pending, Worker-Start
- Worker: speaker gesetzt (Text/Wörter unverändert), failed bei Diar-Fehler,
  skipped bei Versions-Guard (fremde Edits nie überschreiben)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import service as service_mod
from app.models import Recording, User


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Eigene Engine + synchroner Fake-Thread (Worker läuft inline)."""
    from app import db as db_module

    eng = create_engine(f"sqlite:///{tmp_path / 'rediar.db'}")
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(service_mod, "engine", eng)

    class _SyncThread:
        def __init__(self, target=None, args=(), kwargs=None, **kw):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    monkeypatch.setattr("threading.Thread", _SyncThread)
    # Change 115: Der Re-Diarize-Worker startet einen Job-Heartbeat-Thread
    # („aktiv seit Xs"). Im SyncThread-Fake liefe der inline und blockierte
    # endlos in stop.wait() — für die Worker-Logik irrelevant, also No-op.
    monkeypatch.setattr(service_mod, "_start_job_heartbeat",
                        lambda rec_id, interval_s=5.0: threading.Event())
    return eng


def _mk_recording(eng, uid="r1", status="done", audio=True, **kw):
    audio_path = None
    if audio:
        audio_path = Path(eng.url.database).parent / f"{uid}.mp3"
        audio_path.write_bytes(b"MP3DATA")
    with Session(eng) as s:
        s.add(User(id=1, sub="u1"))
        s.add(Recording(
            id=1, uid=uid, original_name=f"{uid}.mp3", stored_path=str(audio_path),
            user_id=1, status=status, text="Hallo Welt",
            segments=[
                {"start": 0.0, "end": 2.0, "text": "Hallo",
                 "words": [{"word": "Hallo", "start": 0.0, "end": 2.0}]},
                {"start": 2.0, "end": 4.0, "text": "Welt",
                 "words": [{"word": "Welt", "start": 2.0, "end": 4.0}]},
            ],
            **kw,
        ))
        s.commit()


@pytest.fixture(autouse=True)
def _diar_mocks(monkeypatch, env):
    def fake_diar(path, **kw):
        return [{"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"}]

    def fake_merge(segments, diar, word_stream, duration, full_text=None):
        out = json.loads(json.dumps(segments))
        for s in out:
            s["speaker"] = "SPEAKER_00"
        return out

    monkeypatch.setattr(service_mod, "_run_diarization", fake_diar)
    monkeypatch.setattr(service_mod, "_merge_diarization", fake_merge)


# ---------------------------------------------------------------------------
# _schedule_rediarize
# ---------------------------------------------------------------------------


def test_schedule_requires_done(env):
    _mk_recording(env, status="uploaded")
    assert service_mod._schedule_rediarize(1) is False
    with Session(env) as s:
        assert s.get(Recording, 1).diar_status == "done"


def test_schedule_missing_audio(env):
    _mk_recording(env, audio=False)
    assert service_mod._schedule_rediarize(1) is False


def test_schedule_enqueues_und_worker_setzt_speaker(env, monkeypatch):
    """Change 155 (Schritt 4): _schedule_rediarize enqueued einen
    rediarize-Queue-Job — der Fake-Queue führt den Worker inline aus
    (deterministisch), Sprecher werden gesetzt, Text/Wörter unangetastet."""
    _mk_recording(env)

    class _InlineQueue:
        def enqueue(self, rec_id, user_id=None, backend=None, priority=0,
                    kind="transcribe", payload=None, key=None):
            assert kind == "rediarize" and key == f"rediarize-{rec_id}"
            assert payload is None  # keine Diar-Optionen übersteuert
            # Universelles Scheduling: der Dispatch ruft den Worker.
            service_mod.run_rediarize_job(rec_id, payload=payload)
            return 1

    monkeypatch.setattr("app.queue.queue_manager", _InlineQueue())
    assert service_mod._schedule_rediarize(1) is True
    with Session(env) as s:
        rec = s.get(Recording, 1)
        assert rec.diar_status == "done"  # Worker lief durch
        assert rec.segments[0]["speaker"] == "SPEAKER_00"
        assert rec.segments[1]["speaker"] == "SPEAKER_00"
        # Text + Wörter unangetastet
        assert rec.text == "Hallo Welt"
        assert rec.segments[0]["words"][0]["start"] == 0.0
        assert rec.alignment == "done"


def test_worker_failed_when_diar_throws(env, monkeypatch):
    from app.diarize import DiarizationError

    _mk_recording(env)
    monkeypatch.setattr(
        service_mod, "_run_diarization",
        lambda path, **kw: (_ for _ in ()).throw(
            DiarizationError("conn", "dienst down")))
    service_mod._run_background_rediarize(1, b"MP3DATA", 0.0)
    with Session(env) as s:
        rec = s.get(Recording, 1)
        assert rec.diar_status == "failed"
        assert rec.segments[0].get("speaker") is None  # unangetastet


def test_worker_skipped_on_version_guard(env, monkeypatch):
    """Segmente seit Worker-Start geändert → Ergebnis verworfen (skipped)."""
    _mk_recording(env)

    def guard_merge(segments, diar, word_stream, duration, full_text=None):
        # Simuliert einen fremden Edit WÄHREND des Laufs.
        with Session(env) as s:
            r = s.get(Recording, 1)
            r.segments = [{"start": 0.0, "end": 1.0, "text": "FREMDER EDIT"}]
            s.add(r)
            s.commit()
        return json.loads(json.dumps(segments))

    monkeypatch.setattr(service_mod, "_merge_diarization", guard_merge)
    service_mod._run_background_rediarize(1, b"MP3DATA", 0.0)
    with Session(env) as s:
        rec = s.get(Recording, 1)
        assert rec.diar_status == "skipped"
        assert rec.segments == [{"start": 0.0, "end": 1.0, "text": "FREMDER EDIT"}]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture()
def _patch_auth(monkeypatch):
    # segments.py authentifiziert via app.identity.current_identity
    from app.identity import Identity

    def _fake_identity(request, session=None):
        return Identity(User(id=1, sub="u1"), None)

    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_identity)


def _call_route(env, uid="r1", user_id=1):
    from app.routers import segments as seg_mod

    with Session(env) as s:
        return seg_mod.re_diarize_recording(
            uid, request=_FakeRequest(session={"user_id": user_id}), session=s)


def test_route_requires_done(env, _patch_auth):
    _mk_recording(env, status="processing")
    with pytest.raises(HTTPException) as ei:
        _call_route(env)
    assert ei.value.status_code == 409


def test_route_conflict_when_running(env, _patch_auth):
    _mk_recording(env, diar_status="running")
    with pytest.raises(HTTPException) as ei:
        _call_route(env)
    assert ei.value.status_code == 409


@pytest.fixture()
def _fake_queue(monkeypatch):
    """Change 155 (Schritt 4): _schedule_rediarize enqueued ins echte
    Singleton — Tests isolieren das (keine echten Worker, kein geteilter
    Zustand über Tests hinweg). Protokolliert die Aufrufe."""
    calls = []

    class _FakeQueue:
        def enqueue(self, rec_id, user_id=None, backend=None, priority=0,
                    kind="transcribe", payload=None, key=None):
            calls.append((rec_id, kind, key, payload))
            return 1

    monkeypatch.setattr("app.queue.queue_manager", _FakeQueue())
    return calls


def test_route_ok(env, _patch_auth, _fake_queue):
    _mk_recording(env)
    out = _call_route(env)
    assert out == {"id": "r1", "diar_status": "pending"}
    # Change 116: Diar-Optionen (Form) werden als payload weitergereicht.
    assert _fake_queue[0][:3] == (1, "rediarize", "rediarize-1")
    assert isinstance(_fake_queue[0][3], dict)


def test_route_503_when_audio_missing(env, _patch_auth):
    _mk_recording(env, audio=False)
    with pytest.raises(HTTPException) as ei:
        _call_route(env)
    assert ei.value.status_code == 503


def test_route_404_unknown(env, _patch_auth):
    _mk_recording(env)
    from app.routers import segments as seg_mod

    with Session(env) as s:
        with pytest.raises(HTTPException) as ei:
            seg_mod.re_diarize_recording(
                "nope", request=_FakeRequest(session={"user_id": 1}), session=s)
        assert ei.value.status_code == 404
