"""Change 150: Diarization meldet echten Server-Fortschritt via /progress.

Der Poller-Thread fragt waehrend des POSTs GET /progress ab und ruft
``on_progress(pct)`` — die Webapp zeigt damit echte Prozente statt einer
Blackbox-Phase.
"""

import time

import httpx
import pytest

from app import diarize as diarize_mod


def test_diarize_reports_progress(monkeypatch, tmp_path):
    calls = []
    state = {"p": 0}

    def handler(request):
        if request.url.path == "/progress":
            state["p"] = min(state["p"] + 50, 100)
            return httpx.Response(200, json={"busy": True, "progress": state["p"]})
        # POST /v1/audio/transcriptions — so lange blockieren, dass der
        # Poller-Thread (Intervall 2 s) mindestens einmal zuschlaegt.
        time.sleep(2.6)
        return httpx.Response(
            200,
            json={"segments": [{"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"}]},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(diarize_mod.settings, "DIAR_URL", "http://diar.test:5098")

    class _Client(httpx.Client):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr(diarize_mod.httpx, "Client", _Client)

    wav = tmp_path / "t.wav"
    wav.write_bytes(b"\x00" * 64)  # Suffix .wav → keine Konvertierung noetig

    segs = diarize_mod.diarize(str(wav), method="pyannote", on_progress=calls.append)

    assert calls, "Poller muss mindestens einen Fortschrittswert geliefert haben"
    assert calls[-1] == 100
    assert segs and segs[0]["speaker"] == "SPEAKER_00"


def test_diarize_ohne_callback_laeuft_normal(monkeypatch, tmp_path):
    def handler(request):
        if request.url.path == "/progress":
            return httpx.Response(200, json={"busy": False, "progress": -1})
        return httpx.Response(
            200,
            json={"segments": [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(diarize_mod.settings, "DIAR_URL", "http://diar.test:5098")

    class _Client(httpx.Client):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr(diarize_mod.httpx, "Client", _Client)

    wav = tmp_path / "t2.wav"
    wav.write_bytes(b"\x00" * 64)
    segs = diarize_mod.diarize(str(wav))  # kein on_progress → kein Poller
    assert segs and segs[0]["speaker"] == "SPEAKER_00"
