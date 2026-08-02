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
            diarize_num_speakers=None, diarize_min_duration_off=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=1, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        rec = s.get(Recording, 1)
        assert rec.prompt_template_id == 1


def test_transcribe_foreign_template_403(db, qm):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r1", _req(1), enable_vad=False, enable_diarize=False,
                diarize_num_speakers=None, diarize_min_duration_off=None,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=None, enable_llm_enhance=None,
                prompt_template_id=2, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert ei.value.status_code == 403


def test_anon_with_template_403(db, qm, monkeypatch):
    monkeypatch.setattr(recordings, "ensure_access", lambda *a, **k: None)
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.transcribe_ep(
                "r1", _req(None), enable_vad=False, enable_diarize=False,
                diarize_num_speakers=None, diarize_min_duration_off=None,
                enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
                enable_punctuation=None, enable_llm_enhance=None,
                prompt_template_id=1, delivery_target_id=None, llm_endpoint_id=None, backend="", session=s)
        assert ei.value.status_code == 403


def test_transcribe_with_target_sets_pending(db, qm):
    with Session(db) as s:
        recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=False,
            diarize_num_speakers=None, diarize_min_duration_off=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=None, delivery_target_id=1, llm_endpoint_id=None, backend="", session=s)
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


def _fake_update_result(session, rec_id, **kw):
    """Wie der echte update_result: schreibt das Ergebnis in die DB-Zeile."""
    r = session.get(Recording, rec_id)
    if r is not None:
        r.status = kw.get("status", "done")
        r.text = kw.get("text") or r.text
        r.language = kw.get("language")
        r.duration_s = kw.get("duration_s")
        if "error" in kw:
            r.error = kw.get("error")
        session.add(r)
        session.commit()


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
    monkeypatch.setattr(service_mod.crud, "update_result", _fake_update_result)
    monkeypatch.setattr(service_mod.crud, "set_progress",
                        lambda session, rec_id, pct: None)
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)
    calls = {}
    monkeypatch.setattr(llm, "chat",
                        lambda system, text, endpoint=None: "Zusammenfassung: ...")
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
    monkeypatch.setattr(service_mod.crud, "update_result", _fake_update_result)
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


def test_service_diarize_gated_marks_failed(db, monkeypatch):
    """Wenn das Diarization-Modell gated ist (Lizenz fehlt), wird die
    Aufnahme NICHT still ohne Speaker fertig — sondern failed mit einer
    Meldung, die den Admin-Hinweis enthält."""
    from app import service as service_mod
    from app import queue as queue_mod
    from app.diarize import DiarizationError

    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(queue_mod.crud, "get_recording",
                        lambda s, rid: s.get(Recording, rid))
    monkeypatch.setattr(service_mod, "get_client", lambda backend: _FakeClient())
    monkeypatch.setattr(service_mod.crud, "update_result", _fake_update_result)
    monkeypatch.setattr(service_mod.crud, "set_progress",
                        lambda session, rec_id, pct: None)
    monkeypatch.setattr(service_mod, "_compute_peaks", lambda b: None)

    def boom(audio_path, num_speakers=None, min_duration_off=None):
        raise DiarizationError(
            "gated",
            "Das Diarization-Modell ist lizenzgeschützt. "
            "Bitte den Administrator informieren, damit er die "
            "Nutzungsbedingungen auf HuggingFace akzeptiert.",
        )

    monkeypatch.setattr(service_mod, "_run_diarization", boom)

    with Session(db) as s:
        rec = s.get(Recording, 1)
        rec.enable_diarize = True
        s.add(rec)
        s.commit()

    service_mod.process_recording(1, backend="pk-python")

    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.status == "failed"
        assert "Administrator" in (rec.error or "")
        assert "lizenzgeschützt" in (rec.error or "")


# ---------------------------------------------------------------------------
# _merge_diarization: Diarization-Segmente bestimmen die Segmentierung
# ---------------------------------------------------------------------------

def test_merge_diarization_replaces_segments_with_speaker_text():
    """Bei aktiver Diarization bestimmen die Diarization-Segmente die
    Anzeige-Segmente; der Text pro Segment kommt aus den Wort-Zeitstempeln."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 21.44, "text": "Hallo hier",
        "words": [
            {"word": "Hallo", "start": 0.0, "end": 0.5},
            {"word": "hier", "start": 0.5, "end": 1.0},
            {"word": "weiblich", "start": 5.0, "end": 5.5},
            {"word": "stimme", "start": 5.5, "end": 6.0},
        ],
    }]
    diar = [
        {"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"},
        {"start": 4.5, "end": 8.0, "speaker": "SPEAKER_01"},
    ]

    merged = service_mod._merge_diarization(asr_segments, diar)

    assert len(merged) == 2
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[0]["text"] == "Hallo hier"
    assert merged[0]["start"] == 0.0 and merged[0]["end"] == 4.0
    assert merged[1]["speaker"] == "SPEAKER_01"
    assert merged[1]["text"] == "weiblich stimme"
    assert len(merged[1]["words"]) == 2


def test_merge_diarization_skips_segments_without_words():
    """Diarization-Segmente ohne zugehörige Wörter (Pausen) werden
    übersprungen — kein leeres Segment in der Anzeige."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 10.0, "text": "Hallo",
        "words": [{"word": "Hallo", "start": 0.0, "end": 1.0}],
    }]
    diar = [
        {"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"},
        {"start": 6.0, "end": 8.0, "speaker": "SPEAKER_01"},  # Pause, keine Wörter
    ]

    merged = service_mod._merge_diarization(asr_segments, diar)

    assert len(merged) == 1
    assert merged[0]["speaker"] == "SPEAKER_00"


def test_merge_diarization_keeps_speaker_per_turn():
    """Mehrere Turns desselben Sprechers bleiben getrennte Segmente
    (kein Zusammenführen über Pausen hinweg)."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 20.0, "text": "",
        "words": [
            {"word": "A", "start": 0.0, "end": 1.0},
            {"word": "B", "start": 10.0, "end": 11.0},
        ],
    }]
    diar = [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
        {"start": 9.0, "end": 12.0, "speaker": "SPEAKER_00"},
    ]

    merged = service_mod._merge_diarization(asr_segments, diar)

    assert len(merged) == 2
    assert [m["speaker"] for m in merged] == ["SPEAKER_00", "SPEAKER_00"]


def test_merge_diarization_words_keep_timestamps_karaoke():
    """Karaoke: Die gemergten Segmente müssen Wörter MIT start/end liefern,
    damit SegmentList die Wörter beim Playback hervorheben kann."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 8.0, "text": "hallo hier",
        "words": [
            {"word": "hallo", "start": 0.0, "end": 1.0},
            {"word": "hier", "start": 1.0, "end": 2.0},
            {"word": "weiblich", "start": 4.0, "end": 5.0},
        ],
    }]
    diar = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
        {"start": 3.5, "end": 6.0, "speaker": "SPEAKER_01"},
    ]

    merged = service_mod._merge_diarization(asr_segments, diar)

    for seg in merged:
        for w in seg["words"]:
            assert "start" in w and "end" in w, \
                f"Wort ohne Timestamp: {w} (Karaoke würde brechen)"
            assert seg["start"] <= w["start"] < w["end"] <= seg["end"] or \
                   w["start"] >= seg["start"], \
                f"Wort {w} außerhalb des Segments {seg['start']}-{seg['end']}"
    # Segment 0: hallo hier; Segment 1: weiblich
    assert merged[0]["words"] == [
        {"word": "hallo", "start": 0.0, "end": 1.0},
        {"word": "hier", "start": 1.0, "end": 2.0},
    ]
    assert merged[1]["words"] == [{"word": "weiblich", "start": 4.0, "end": 5.0}]


def test_merge_diarization_word_overlap_at_boundary():
    """Karaoke-Kante: Ein Wort, dessen start exakt an der Segmentgrenze
    liegt, gehört zum nächsten Segment (start < end-Regel)."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 6.0, "text": "",
        "words": [
            {"word": "a", "start": 0.0, "end": 1.0},
            {"word": "b", "start": 3.0, "end": 4.0},  # start == d_end von Seg 0
        ],
    }]
    diar = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
        {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
    ]

    merged = service_mod._merge_diarization(asr_segments, diar)

    assert merged[0]["words"] == [{"word": "a", "start": 0.0, "end": 1.0}]
    assert merged[1]["words"] == [{"word": "b", "start": 3.0, "end": 4.0}]


def test_merge_diarization_no_segments_without_speaker():
    """Jedes gemergte Segment trägt einen Speaker (Karaoke-Badge + SRT)."""
    from app import service as service_mod

    asr_segments = [{
        "start": 0.0, "end": 10.0, "text": "",
        "words": [{"word": "x", "start": 0.0, "end": 1.0}],
    }]
    diar = [{"start": 0.0, "end": 5.0, "speaker": "SPEAKER_07"}]

    merged = service_mod._merge_diarization(asr_segments, diar)

    assert len(merged) == 1
    assert merged[0]["speaker"] == "SPEAKER_07"
