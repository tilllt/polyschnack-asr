"""CrispASR (ark-asr) HTTP-Adapter: spricht den crispasr-Server im Container an.

CrispASR hat einen OpenAI-kompatiblen Server-Modus (``crispasr --server``):
POST /v1/audio/transcriptions mit verbose_json. Der Webapp-Adapter nutzt
diesen HTTP-Endpunkt statt eines lokalen CLI-Binaries.
"""
import httpx
import pytest

from app.asr_client.adapters.crisp_asr_http import CrispAsrHttpClient


def _verbose_json():
    return {
        "task": "transcribe",
        "language": "de",
        "duration": 4.0,
        "text": "Guten Tag",
        "segments": [
            {
                "id": 0, "start": 0.0, "end": 2.0, "text": "Guten Tag",
                "words": [{"word": "Guten", "start": 0.0, "end": 1.0},
                          {"word": "Tag", "start": 1.0, "end": 2.0}],
            },
        ],
    }


def _client(responses, url="http://ark-asr:5095"):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses.pop(0)
        if isinstance(resp, httpx.Response):
            return resp
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    return CrispAsrHttpClient(url=url, transport=transport)


def test_crisp_http_transcribe_parses_segments():
    client = _client([_verbose_json()])
    result = client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Guten Tag"
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text"] == "Guten Tag"
    assert result["duration"] == 4.0
    assert result["language"] == "de"


def test_crisp_http_posts_to_openai_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["files"] = b'name="file"' in request.content
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = CrispAsrHttpClient(url="http://ark-asr:5095", transport=transport)
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "/v1/audio/transcriptions" in seen["url"]
    assert seen["files"]


def test_crisp_http_http_error_raises():
    client = _client([httpx.Response(503, text="model not loaded")])
    with pytest.raises(Exception) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "503" in str(ei.value)


def test_crisp_http_capabilities():
    c = CrispAsrHttpClient()
    assert c.capabilities.label == "ark-asr"
    assert c.capabilities.word_timestamps is True
