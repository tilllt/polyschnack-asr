"""qwen3-Adapter (HTTP): spricht den qwen3-asr-server im Container an.

OpenAI-kompatibles POST /v1/audio/transcriptions (verbose_json) — wie
pk_cpp. Der Server lebt im eigenen Container (qwen3-asr:8080); die Webapp
hat kein qwen3-asr-cli mehr nötig.
"""
import httpx
import pytest

from app.asr_client.adapters.qwen3_asr_http import Qwen3AsrHttpClient


def _verbose_json():
    return {
        "task": "transcribe",
        "language": "de",
        "duration": 5.0,
        "text": "Hallo Welt",
        "segments": [
            {
                "id": 0, "start": 0.0, "end": 1.2, "text": "Hallo",
                "words": [{"word": "Hallo", "start": 0.0, "end": 0.6}],
            },
            {
                "id": 1, "start": 1.2, "end": 2.4, "text": "Welt",
                "words": [{"word": "Welt", "start": 1.2, "end": 2.4}],
            },
        ],
    }


def _client(responses, url="http://qwen3-asr:8080"):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses.pop(0)
        if isinstance(resp, httpx.Response):
            return resp
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    return Qwen3AsrHttpClient(url=url, transport=transport)


def test_qwen3_http_transcribe_parses_segments():
    client = _client([_verbose_json()])
    result = client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Hallo Welt"
    assert len(result["segments"]) == 2
    assert result["segments"][0]["text"] == "Hallo"
    assert result["segments"][0]["start"] == 0.0
    assert result["duration"] == 5.0
    assert result["language"] == "de"


def test_qwen3_http_posts_to_openai_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["files"] = b'name="file"' in request.content  # multipart body
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = Qwen3AsrHttpClient(url="http://qwen3-asr:8080", transport=transport)
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "/v1/audio/transcriptions" in seen["url"]
    assert seen["files"]


def test_qwen3_http_http_error_raises():
    client = _client([httpx.Response(500, text="boom")])
    with pytest.raises(Exception) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "500" in str(ei.value) or "boom" in str(ei.value)


def test_qwen3_http_connect_error_has_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)

    transport = httpx.MockTransport(handler)
    client = Qwen3AsrHttpClient(url="http://qwen3-asr:8080", transport=transport)
    with pytest.raises(RuntimeError) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "qwen3-asr" in str(ei.value)
    assert "Container" in str(ei.value)


def test_qwen3_http_capabilities():
    c = Qwen3AsrHttpClient()
    assert c.capabilities.label == "qwen3-asr"
    assert c.capabilities.word_timestamps is True
