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
