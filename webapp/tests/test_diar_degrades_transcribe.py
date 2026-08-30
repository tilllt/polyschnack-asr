"""Change 157: Diar-Fehler degradieren statt Run abbrechen.

- Ohne enable_diarize wird der Diar-Service NIE kontaktiert (Invariante,
  User-Anforderung 2026-08-30: „ASR-Run ohne Diarization darf nicht
  abbrechen, weil der Diar-Container nicht läuft").
- Mit enable_diarize + DiarizationError (z.B. service-unreachable) bleibt
  der Run done — Text + Segmente werden persistiert, diar_status="failed"
  und error tragen den ehrlichen Hinweis (kein stiller Fehler).
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import service as service_mod
from app.diarize import DiarizationError
from app.models import Recording, TranscriptionRun, User


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/diar.db")
    SQLModel.metadata.create_all(eng)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3")
    with Session(eng) as s:
        s.add(User(id=1, sub="u1", kind="oidc"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3",
                        stored_path=str(audio), user_id=1, status="uploaded"))
        s.commit()
    return eng


def _mk_client(text="Hallo", duration=1.0, segments=None):
    class _FakeCaps:
        streaming = False
        async_jobs = False
        accepts_compressed = True
        native_punctuation = False

    class _FakeClient:
        capabilities = _FakeCaps()

        def transcribe_async(self, audio_bytes, filename, mime,
                             noise_reduce=True, on_progress=None):
            return {
                "text": text,
                "duration": duration,
                "language": "de",
                "segments": segments or [{"start": 0.0, "end": 1.0, "text": text}],
            }

    return _FakeClient()


def _queue_run(db, enable_diarize=False, **run_kwargs):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        run = TranscriptionRun(
            rec_id=1, status="queued", backend="ps-pk-onnx",
            enable_vad=False, enable_diarize=enable_diarize,
            enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=False, enable_llm_enhance=False,
            **run_kwargs,
        )
        s.add(run)
        s.commit()
        rec.current_run_id = run.id
        rec.backend = "ps-pk-onnx"
        s.add(rec)
        s.commit()
        return run.id


def test_ohne_diarize_wird_diar_service_nie_kontaktiert(db, monkeypatch):
    """Invariante: enable_diarize=False → app.diarize.diarize wird nie
    aufgerufen; der Run wird done ohne diar_status/error."""
    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _mk_client())
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise AssertionError(
            "Diar-Service wurde trotz enable_diarize=False kontaktiert!"
        )

    monkeypatch.setattr("app.diarize.diarize", _boom)
    _queue_run(db, enable_diarize=False)

    service_mod.process_recording(1, backend="ps-pk-onnx")

    assert calls == []
    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.status == "done"
        assert rec.text == "Hallo"
        # Modell-Default ist "done" (keine offenen Diar-Aufgaben) — der
        # Diar-Fehlerpfad ("failed") darf hier NICHT aktiviert worden sein.
        assert rec.diar_status == "done"
        assert rec.error is None


def test_diar_unreachable_degradiert_run_nicht_failed(db, monkeypatch):
    """enable_diarize=True + DiarizationError (service-unreachable) → Run
    bleibt done, Text+Segmente persistiert, diar_status=failed + error."""
    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _mk_client())
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    def _diar_boom(*a, **k):
        raise DiarizationError(
            "service-unreachable",
            "Der Diarization-Service ist nicht erreichbar. Bitte den "
            "Administrator informieren (Container 'diar' prüfen).",
        )

    monkeypatch.setattr("app.diarize.diarize", _diar_boom)
    _queue_run(db, enable_diarize=True, diarize_method="foxnose")

    service_mod.process_recording(1, backend="ps-pk-onnx")

    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.status == "done"
        assert rec.text == "Hallo"
        assert rec.segments  # Segmente bleiben erhalten
        assert rec.diar_status == "failed"
        assert "nicht erreichbar" in (rec.error or "")
