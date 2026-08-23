"""Change 094 — runs → results: Run-Snapshot (Settings), Result, API.

Deckt ab:
- process_recording legt beim Abschluss Run (done) + Result an; die
  Settings des Laufs sind der Snapshot der Recording-Settings bei
  Job-Start; Recording-Zeiger (current_run_id/current_result_id) zeigen
  auf die neuen Einträge.
- Fehlerpfad: Job-Exception → Run failed + error; _abort_recording →
  aktiver Run failed.
- GET /api/recordings/{rid}/runs: Settings-Snapshot, neueste zuerst,
  result_id/segment_count; User-Isolation; 404.
- GET /api/recordings/{rid}/runs/{run_id}: Run + volle Results.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app import service as service_mod
from app.models import Recording, TranscriptionResult, TranscriptionRun, User


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    from app.routers import recordings

    monkeypatch.setattr(
        recordings,
        "_current_user",
        lambda request, session=None: request.session.get("user_id"),
    )


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/runs.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3")
    with Session(eng) as s:
        s.add(User(id=1, sub="u1", kind="oidc"))
        s.add(User(id=2, sub="u2", kind="oidc"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="uploaded"))
        s.add(Recording(id=2, uid="r2", original_name="fremd.mp3",
                        stored_path=str(audio), user_id=2, status="uploaded"))
        s.commit()
    return eng


def _mk_client(text="Hallo", duration=1.0, language="de", segments=None,
               fail=None):
    class _FakeCaps:
        streaming = False
        async_jobs = False
        accepts_compressed = True
        native_punctuation = False

    class _FakeClient:
        capabilities = _FakeCaps()

        def transcribe_async(self, audio_bytes, filename, mime,
                             noise_reduce=True, on_progress=None):
            if fail is not None:
                raise RuntimeError(fail)
            return {
                "text": text,
                "duration": duration,
                "language": language,
                "segments": segments or [{"start": 0.0, "end": 1.0, "text": text}],
            }

    return _FakeClient()


# ---------------------------------------------------------------------------
# Job-Pfad: Run + Result
# ---------------------------------------------------------------------------


def test_transcribe_erzeugt_run_mit_settings_und_result(db, monkeypatch):
    """Job → Run (Settings aus dem queued-Run, done) + Result + Zeiger."""
    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _mk_client())
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    with Session(db) as s:
        rec = s.get(Recording, 1)
        # Change 099: Settings leben im queued-Run — process_recording
        # übernimmt den ältesten queued-Run (Recording trägt keine Settings).
        run = TranscriptionRun(
            rec_id=1, status="queued",
            backend="ps-pk-onnx", language="de",
            enable_vad=True, enable_diarize=True,
            diarize_num_speakers=2, diarize_min_duration_off=0.5,
            diarize_method="pyannote",
            enable_noise_reduce=True, enable_enhance="light",
            enable_punctuation=True, enable_llm_enhance=False,
        )
        s.add(run)
        s.commit()
        rec.current_run_id = run.id
        rec.backend = "ps-pk-onnx"
        rec.language = "de"
        s.add(rec)
        s.commit()

    service_mod.process_recording(1, backend="ps-pk-onnx")

    with Session(db) as s:
        runs = s.exec(select(TranscriptionRun)).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.rec_id == 1
        assert run.status == "done"
        assert run.finished_at is not None
        assert run.started_at is not None
        assert run.backend == "ps-pk-onnx"
        # Settings == queued-Run-Settings (versionierte Wahrheit)
        assert run.enable_vad is True
        assert run.enable_diarize is True
        assert run.diarize_num_speakers == 2
        assert run.diarize_min_duration_off == 0.5
        assert run.diarize_method == "pyannote"
        assert run.enable_noise_reduce is True
        assert run.enable_enhance == "light"
        assert run.enable_punctuation is True
        assert run.enable_llm_enhance is False

        results = s.exec(
            select(TranscriptionResult).where(TranscriptionResult.run_id == run.id)
        ).all()
        assert len(results) == 1
        assert results[0].text == "Hallo"
        assert results[0].segments and results[0].segments[0]["text"] == "Hallo"

        rec = s.get(Recording, 1)
        assert rec.current_run_id == run.id
        assert rec.current_result_id == results[0].id
        # Spiegel unverändert (Anzeige = Export bleibt)
        assert rec.text == "Hallo"
        assert rec.status == "done"


def test_job_fehler_markiert_run_failed(db, monkeypatch):
    """Job-Exception → aktiver Run failed + error, kein Result."""
    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(service_mod, "get_client",
                        lambda backend: _mk_client(fail="boom"))
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    service_mod.process_recording(1, backend="ps-pk-onnx")

    with Session(db) as s:
        runs = s.exec(select(TranscriptionRun)).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "boom" in (runs[0].error or "")
        results = s.exec(select(TranscriptionResult)).all()
        assert len(results) == 0


def test_abort_markiert_run_failed(db, monkeypatch):
    """_abort_recording → aktiver Run failed + error."""
    monkeypatch.setattr(service_mod, "engine", db)
    with Session(db) as s:
        run = TranscriptionRun(rec_id=1, backend="ps-pk-onnx",
                               status="processing")
        s.add(run)
        s.commit()
        s.refresh(run)
        rec = s.get(Recording, 1)
        rec.current_run_id = run.id
        s.add(rec)
        s.commit()

    service_mod._abort_recording(1, "abgebrochen")

    with Session(db) as s:
        run = s.get(TranscriptionRun, 1)
        assert run.status == "failed"
        assert run.error == "abgebrochen"
        assert run.finished_at is not None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _seed_runs(db):
    with Session(db) as s:
        s.add(TranscriptionRun(id=1, rec_id=1, backend="ps-pk-onnx",
                               status="done", enable_vad=True,
                               enable_diarize=False, duration_s=1.0))
        s.add(TranscriptionRun(id=2, rec_id=1, backend="crispr-pk-cpp",
                               status="done", enable_vad=False,
                               enable_diarize=True, duration_s=1.5))
        s.add(TranscriptionResult(id=1, run_id=1, text="alt",
                                  segments=[{"start": 0.0, "end": 1.0, "text": "alt"}]))
        s.add(TranscriptionResult(id=2, run_id=2, text="neu",
                                  segments=[
                                      {"start": 0.0, "end": 0.5, "text": "neu"},
                                      {"start": 0.5, "end": 1.0, "text": "dings"},
                                  ]))
        s.commit()


def test_list_runs_api(db):
    from app.routers import recordings

    _seed_runs(db)
    with Session(db) as s:
        out = recordings.list_runs_endpoint(
            "r1", request=_FakeRequest(session={"user_id": 1}), session=s)
        runs = out["runs"]
        # neueste zuerst
        assert [r["id"] for r in runs] == [2, 1]
        r2, r1 = runs
        assert r1["status"] == "done"
        assert r1["backend"] == "ps-pk-onnx"
        assert r1["settings"]["enable_vad"] is True
        assert r1["settings"]["enable_diarize"] is False
        assert r1["result_id"] == 1
        assert r1["segment_count"] == 1
        assert r2["settings"]["enable_vad"] is False
        assert r2["settings"]["enable_diarize"] is True
        assert r2["result_id"] == 2
        assert r2["segment_count"] == 2
        assert r2["duration_s"] == 1.5


def test_list_runs_api_user_isolated(db):
    """Fremder User (kein Owner/Share) → kein Zugriff."""
    from app.routers import recordings

    _seed_runs(db)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.list_runs_endpoint(
                "r1", request=_FakeRequest(session={"user_id": 99}), session=s)
        assert ei.value.status_code in (401, 403)


def test_list_runs_api_404(db):
    from app.routers import recordings

    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.list_runs_endpoint(
                "gibtsnicht", request=_FakeRequest(session={"user_id": 1}), session=s)
        assert ei.value.status_code == 404


def test_get_run_api_mit_result(db):
    from app.routers import recordings

    _seed_runs(db)
    with Session(db) as s:
        out = recordings.get_run_endpoint(
            "r1", 2, request=_FakeRequest(session={"user_id": 1}), session=s)
        assert out["id"] == 2
        assert out["settings"]["enable_diarize"] is True
        assert out["results"][0]["text"] == "neu"
        assert len(out["results"][0]["segments"]) == 2


def test_get_run_api_404_fremder_run(db):
    """Run existiert, gehört aber zu einer anderen Recording → 404."""
    from app.routers import recordings

    _seed_runs(db)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.get_run_endpoint(
                "r2", 1, request=_FakeRequest(session={"user_id": 2}), session=s)
        assert ei.value.status_code == 404
