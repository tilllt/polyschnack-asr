"""Diarization-Fehlererkennung: Lizenz/gated-Fehler müssen als präzise
Fehlermeldung mit Admin-Hinweis ankommen statt still verschluckt zu werden."""
import pytest

from app.diarize import DiarizationError, _classify_load_error, diarize


# ---------------------------------------------------------------------------
# Fehlerklassifizierung
# ---------------------------------------------------------------------------

def test_classify_403_gated():
    class FakeResp:
        status_code = 403
    class FakeExc(Exception):
        def __init__(self):
            super().__init__("Cannot access gated repo for url ...")
            self.response = FakeResp()
    code, msg = _classify_load_error(FakeExc())
    assert code == "gated"
    assert "license" in msg.lower() or "lizenz" in msg.lower()
    assert "admin" in msg.lower()


def test_classify_404_not_found():
    class FakeResp:
        status_code = 404
    class FakeExc(Exception):
        def __init__(self):
            super().__init__("Entry not found")
            self.response = FakeResp()
    code, msg = _classify_load_error(FakeExc())
    assert code == "not-found"


def test_classify_401_unauthorized():
    class FakeResp:
        status_code = 401
    class FakeExc(Exception):
        def __init__(self):
            super().__init__("Invalid token")
            self.response = FakeResp()
    code, msg = _classify_load_error(FakeExc())
    assert code == "unauthorized"


def test_classify_gated_text_without_response():
    """Auch ohne .response-Attribut: 'gated' im Text → gated."""
    class FakeExc(Exception):
        pass
    exc = FakeExc("Gated repo: you must agree to terms first")
    code, _ = _classify_load_error(exc)
    assert code == "gated"


def test_classify_unknown():
    class FakeExc(Exception):
        pass
    code, msg = _classify_load_error(FakeExc("some random error"))
    assert code == "load-failed"


# ---------------------------------------------------------------------------
# DiarizationError Datentyp
# ---------------------------------------------------------------------------

def test_diarization_error_carries_code_and_message():
    e = DiarizationError("gated", "Lizenz fehlt — Admin informieren.")
    assert e.code == "gated"
    assert "Admin" in e.message
    assert "gated" in str(e)


# ---------------------------------------------------------------------------
# diarize() propagiert Ladefehler (kein stilles [] mehr)
# ---------------------------------------------------------------------------

def test_diarize_propagates_load_error(monkeypatch):
    """Wenn _load_pipeline eine DiarizationError wirft, muss diarize() sie
    durchreichen — der Aufrufer (service.py) markiert die Aufnahme dann
    als failed mit präziser Meldung."""
    def boom():
        raise DiarizationError("gated", "Lizenz fehlt — Admin informieren.")
    monkeypatch.setattr("app.diarize._load_pipeline", boom)
    with pytest.raises(DiarizationError) as ei:
        diarize("/tmp/nonexistent.wav")
    assert ei.value.code == "gated"


def test_diarize_no_token(monkeypatch):
    """Ohne HF_TOKEN muss _load_pipeline eine DiarizationError werfen
    (kein stilles None → leere Liste)."""
    monkeypatch.setattr("app.diarize.os.getenv", lambda k, d=None: None)
    with pytest.raises(DiarizationError) as ei:
        diarize("/tmp/nonexistent.wav")
    assert ei.value.code == "no-token"
    assert "admin" in ei.value.message.lower() or "Admin" in ei.value.message


# ---------------------------------------------------------------------------
# _extract_segments: pyannote 4.x DiarizeOutput vs 3.x Annotation
# ---------------------------------------------------------------------------

def test_extract_segments_pyannote4_serialize():
    """pyannote 4.x: Ergebnis ist DiarizeOutput mit serialize() → dict."""
    from app.diarize import _extract_segments

    class FakeOutput:
        def serialize(self):
            return {"diarization": [
                {"start": 0.1, "end": 2.5, "speaker": "SPEAKER_00"},
                {"start": 2.8, "end": 5.0, "speaker": "SPEAKER_01"},
            ]}

    segs = _extract_segments(FakeOutput())
    assert len(segs) == 2
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert segs[1]["end"] == 5.0


def test_extract_segments_pyannote4_speaker_diarization_attr():
    """pyannote 4.x ohne serialize: .speaker_diarization Annotation nutzen."""
    from app.diarize import _extract_segments

    class FakeTurn:
        start = 1.0
        end = 3.0

    class FakeAnnotation:
        def itertracks(self, yield_label=True):
            yield (FakeTurn(), None, "SPEAKER_00")

    class FakeOutput:
        speaker_diarization = FakeAnnotation()

    segs = _extract_segments(FakeOutput())
    assert segs == [{"start": 1.0, "end": 3.0, "speaker": "SPEAKER_00"}]


def test_extract_segments_pyannote3_annotation():
    """pyannote 3.x: Ergebnis ist direkt eine Annotation mit itertracks."""
    from app.diarize import _extract_segments

    class FakeTurn:
        start = 0.5
        end = 1.5

    class FakeAnnotation:
        def itertracks(self, yield_label=True):
            yield (FakeTurn(), None, "SPEAKER_00")
            yield (FakeTurn(), None, "SPEAKER_01")

    segs = _extract_segments(FakeAnnotation())
    assert len(segs) == 2
    assert {s["speaker"] for s in segs} == {"SPEAKER_00", "SPEAKER_01"}


def test_extract_segments_unknown_format():
    from app.diarize import _extract_segments

    class Weird:
        pass

    assert _extract_segments(Weird()) == []
