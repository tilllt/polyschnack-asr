"""Change 011: Heartbeat-Threads in stillen Phasen (Sync-ASR, Diarization).

Ein blockierender transcribe()-Call (Sync-Backend ohne Job-Progress) darf
das Frontend nicht einfrieren lassen: last_heartbeat_at muss währenddessen
ticken („läuft, aktiv seit Xs"), ohne dass progress_pct sich bewegt
(kein erfundener Fortschritt).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Recording


@pytest.fixture()
def db(tmp_path):
    # check_same_thread=False: Heartbeat-Thread öffnet eigene Sessions,
    # während die Main-Session offen ist — sonst flaky (SQLite-Lock).
    eng = create_engine(
        f"sqlite:///{tmp_path}/hb.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _mk(db, status="processing"):
    with Session(db) as s:
        rec = Recording(
            uid="hb-1", original_name="a.m4a", mime="audio/mp4",
            stored_path="/tmp/a.m4a", size_bytes=100,
            status=status, progress_pct=1,
        )
        s.add(rec)
        s.commit()
        return rec.id


def _wait_for(fn, timeout_s=3.0, interval_s=0.02):
    """Poll bis fn() truthy ist (Thread-Timing entkoppeln)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(interval_s)
    return False


def test_heartbeat_thread_ticks_last_heartbeat_at(db, monkeypatch):
    """_start_heartbeat aktualisiert last_heartbeat_at periodisch (Change 011)."""
    from app import service as service_mod

    monkeypatch.setattr(service_mod, "engine", db)  # Thread schreibt in Test-DB
    rec_id = _mk(db)

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.last_heartbeat_at is None

    stop = service_mod._start_heartbeat(rec_id, 21, "asr", interval_s=0.05)

    try:
        # Auf den ersten Tick warten (Thread-Scheduling).
        def _ticked():
            with Session(db) as s:
                return s.get(Recording, rec_id).last_heartbeat_at is not None

        assert _wait_for(_ticked), "Heartbeat-Tick kam nie an"

        with Session(db) as s:
            rec = s.get(Recording, rec_id)
            first = rec.last_heartbeat_at
            assert first is not None
            # Change 035: Heartbeat liest den pct aus der DB — er schreibt
            # nie einen erfundenen Wert (pct bleibt 1 aus _mk, nicht fix 21).
            assert rec.progress_pct == 1
            assert rec.progress_note == "asr"

        # Auf einen WEITEREN Tick warten (timestamp muss sich bewegen).
        def _advanced():
            with Session(db) as s:
                hb = s.get(Recording, rec_id).last_heartbeat_at
                return hb is not None and hb > first

        assert _wait_for(_advanced), "Heartbeat tickte nicht weiter"

        with Session(db) as s:
            rec = s.get(Recording, rec_id)
            assert rec.last_heartbeat_at > first
            # pct bewegt sich NICHT (kein erfundener Fortschritt)
            assert rec.progress_pct == 1
            assert rec.progress_note == "asr"
    finally:
        stop.set()


def test_heartbeat_stops_when_event_set(db, monkeypatch):
    """Nach stop.set() tickt der Heartbeat nicht weiter (kein Leak)."""
    from app import service as service_mod

    monkeypatch.setattr(service_mod, "engine", db)
    rec_id = _mk(db)
    stop = service_mod._start_heartbeat(rec_id, 96, "diarization", interval_s=0.05)

    # Erst auf einen Tick warten, dann stoppen.
    def _ticked():
        with Session(db) as s:
            return s.get(Recording, rec_id).last_heartbeat_at is not None

    assert _wait_for(_ticked), "Heartbeat-Tick kam nie an"

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.last_heartbeat_at is not None

    stop.set()

    # Sicherstellen, dass der Thread nach dem Stop noch ein paar
    # Intervall-Längen Zeit hatte (und nichts mehr schreibt).
    time.sleep(0.2)

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        frozen = rec.last_heartbeat_at

    time.sleep(0.2)

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.last_heartbeat_at == frozen  # kein weiterer Tick


def test_sync_asr_heartbeat_during_blocking_transcribe(db, monkeypatch):
    """Sync-Backend (async_jobs=False): Heartbeat tickt während des
    blockierenden transcribe; danach 95/finalizing — Prozess normal."""
    from app import service as service_mod

    monkeypatch.setattr(service_mod, "engine", db)
    # LLM/Diarize/Aligner/Peaks aus — nur der ASR-Pfad zählt
    rec_id = _mk(db)

    audio = Path(db.url.database).parent / "a.m4a"
    audio.write_bytes(b"M4A")

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        rec.stored_path = str(audio)
        rec.enable_vad = False
        rec.enable_diarize = False
        rec.enable_streaming = False
        rec.enable_noise_reduce = False
        rec.enable_enhance = "off"
        rec.enable_punctuation = False
        rec.enable_llm_enhance = False
        rec.prompt_template_id = None
        rec.delivery_target_id = None
        rec.llm_endpoint_id = None
        s.add(rec)
        s.commit()

    class _FakeCaps:
        streaming = False
        async_jobs = False  # Sync-Backend → Heartbeat-Pfad
        accepts_compressed = True

    started = threading.Event()
    heartbeat_seen = threading.Event()

    class _FakeClient:
        capabilities = _FakeCaps()

        def transcribe_async(self, audio_bytes, filename, mime,
                             noise_reduce=True, on_progress=None):
            started.set()
            # blockiert 1.2 s — währenddessen muss der Heartbeat ticken
            end = time.monotonic() + 1.2
            while time.monotonic() < end:
                with Session(db) as s:
                    rec = s.get(Recording, rec_id)
                    if rec and rec.last_heartbeat_at is not None:
                        # Heartbeat hat geschrieben → Testziel erreicht
                        pass
                time.sleep(0.05)
            return {"text": "Hallo", "duration": 1.0, "language": "de",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]}

    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    # set_progress real verwenden (echte Heartbeat-Logik), aber Session-Engine
    # ist der Test-db → service_mod.engine wurde gepatcht. set_progress nutzt
    # den übergebenen Session — passt.
    service_mod.process_recording(rec_id, backend="ps-pk-onnx")

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.status == "done"
        assert rec.text == "Hallo"
        assert rec.last_heartbeat_at is not None


def test_heartbeat_ticks_trotz_async_jobs_true(db, monkeypatch):
    """Change 035: ps-pk-onnx deklariert async_jobs=True, definiert aber kein
    eigenes transcribe_async → blockierender Sync-Fallback. Der Heartbeat
    MUSS auch dann ticken, sonst friert die UI ein und zeigt bei JEDER
    Transkription die (falsche) Stall-Warnung."""
    import datetime as dt

    from app import service as service_mod

    monkeypatch.setattr(service_mod, "engine", db)
    rec_id = _mk(db)

    audio = Path(db.url.database).parent / "async_fallback.m4a"
    audio.write_bytes(b"M4A")

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        rec.stored_path = str(audio)
        rec.enable_vad = False
        rec.enable_diarize = False
        rec.enable_streaming = False
        rec.enable_noise_reduce = False
        rec.enable_enhance = "off"
        rec.enable_punctuation = False
        rec.enable_llm_enhance = False
        rec.prompt_template_id = None
        rec.delivery_target_id = None
        rec.llm_endpoint_id = None
        s.add(rec)
        s.commit()

    class _FakeCaps:
        streaming = False
        async_jobs = True  # ← der ps-pk-onnx-Fall (Sync-Fallback!)
        accepts_compressed = True

    beats = []

    class _FakeClient:
        capabilities = _FakeCaps()

        def transcribe_async(self, audio_bytes, filename, mime,
                             noise_reduce=True, on_progress=None):
            # blockiert wie der Sync-Fallback — Heartbeat muss ticken
            end = time.monotonic() + 1.2
            while time.monotonic() < end:
                with Session(db) as s:
                    rec = s.get(Recording, rec_id)
                    if rec and rec.last_heartbeat_at is not None:
                        beats.append(rec.last_heartbeat_at.isoformat())
                time.sleep(0.05)
            return {"text": "Hallo", "duration": 1.0, "language": "de",
                    "segments": []}

    # Schnelleres Heartbeat-Intervall für den Test (echte Logik, nur Timer
    # beschleunigt) — sonst tickt der 5-s-Default im 1.2-s-Fenster kaum.
    real_hb = service_mod._start_heartbeat
    monkeypatch.setattr(
        service_mod, "_start_heartbeat",
        lambda rec_id_, pct, note: real_hb(rec_id_, pct, note, interval_s=0.05),
    )
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    service_mod.process_recording(rec_id, backend="ps-pk-onnx")

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.status == "done"
        assert rec.last_heartbeat_at is not None
        assert rec.progress_note is None or rec.progress_note != "asr"

    # Der Heartbeat muss während des blockierenden Calls MEHRFACH getickt
    # haben — vor Change 035 blieb last_heartbeat_at bei „20% asr" stehen.
    assert len(beats) >= 2, f"Heartbeat tickte nicht (nur {len(beats)}× gesehen)"


def test_set_processing_resets_heartbeat_fields(db):
    """Change 035: set_processing setzt last_heartbeat_at/phase_started_at
    frisch — ein uralter Wert vom letzten Lauf darf nie mehr durchscheinen."""
    import datetime as dt

    from app import crud

    rec_id = _mk(db, status="uploaded")
    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        old = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        rec.last_heartbeat_at = old
        rec.phase_started_at = old
        s.add(rec)
        s.commit()

    with Session(db) as s:
        crud.set_processing(s, rec_id)

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.status == "processing"
        assert rec.last_heartbeat_at is not None
        assert rec.last_heartbeat_at.year == dt.datetime.now(
            dt.timezone.utc).year
        assert rec.phase_started_at == rec.last_heartbeat_at


def test_set_queued_resets_heartbeat_fields(db):
    """Change 035: set_queued resettet die Heartbeat-Felder (wie
    set_processing) — Wartezeit zählt ab Enqueue, nicht ab letztem Lauf."""
    import datetime as dt

    from app import crud

    rec_id = _mk(db, status="uploaded")
    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        old = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        rec.last_heartbeat_at = old
        rec.phase_started_at = old
        s.add(rec)
        s.commit()

    with Session(db) as s:
        crud.set_queued(s, rec_id, backend="ps-pk-onnx")

    with Session(db) as s:
        rec = s.get(Recording, rec_id)
        assert rec.status == "queued"
        assert rec.last_heartbeat_at is not None
        assert rec.last_heartbeat_at.year == dt.datetime.now(
            dt.timezone.utc).year
        assert rec.phase_started_at == rec.last_heartbeat_at
