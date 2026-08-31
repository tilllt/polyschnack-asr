"""Change 173 — max. EIN Job pro Recording.

Befund (2026-08-31): transcribe (Key=rec_id), align ("align-{rec_id}") und
rediarize ("rediarize-{rec_id}") hatten verschiedene Queue-Keys — re-
transcribe + realign liefen parallel (Live-Test Recording 49b7b10a:
crispr-sep-409, Aligner skipped). Der Guard verhindert jetzt JEDEN zweiten
Job auf derselben Recording, solange einer aktiv ist.
"""

import pytest

from app.queue import QueueManager, QueueError


def _queue(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module

    eng = create_engine(
        f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    q = QueueManager(max_queue_len=20)
    # Keine Worker: Jobs bleiben in _jobs, Assertions sind deterministisch.
    monkeypatch.setattr(q, "_ensure_workers", lambda: None)
    return q


def test_zweiter_job_gleiche_recording_abgelehnt(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch)
    q.enqueue(1, None, "ps-pk-onnx", kind="transcribe")
    # realign auf DIESELBE Recording — anderer Key, muss trotzdem scheitern
    with pytest.raises(QueueError):
        q.enqueue(1, None, "align", kind="align", key="align-1")
    # rediarize ebenfalls
    with pytest.raises(QueueError):
        q.enqueue(1, None, "align", kind="rediarize", key="rediarize-1")


def test_verschiedene_recordings_parallel_ok(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch)
    q.enqueue(1, None, "ps-pk-onnx", kind="transcribe")
    q.enqueue(2, None, "ps-pk-onnx", kind="transcribe")  # andere Recording: ok
    q.enqueue(3, None, "align", kind="align", key="align-3")  # wieder andere
    assert len(q._jobs) == 3
