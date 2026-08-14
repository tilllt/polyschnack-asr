"""OpenAI-kompatibler Remote-Adapter: spricht /audio/transcriptions im
OpenAI-Format (verbose_json) mit Bearer-Auth — für OpenAI Whisper,
Mistral Voxtral, Groq und andere Anbieter mit Whisper-API."""

import httpx
import pytest

from app.asr_client.adapters.openai_compat_http import OpenAiCompatHttpClient


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


def _client(responses, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses.pop(0)
        if isinstance(resp, httpx.Response):
            return resp
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    return OpenAiCompatHttpClient(url="https://api.openai.com/v1",
                                  transport=transport, **kwargs)


def test_remote_transcribe_parses_segments():
    client = _client([_verbose_json()])
    result = client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Hallo Welt"
    assert len(result["segments"]) == 2
    assert result["segments"][0]["text"] == "Hallo"
    assert result["segments"][0]["start"] == 0.0
    assert result["duration"] == 5.0
    assert result["language"] == "de"


def test_remote_posts_whisper_endpoint_with_key_and_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode("utf-8", "replace")
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = OpenAiCompatHttpClient(
        url="https://api.openai.com/v1",
        api_key="sk-test",
        model="whisper-1",
        transport=transport,
    )
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert seen["url"].endswith("/audio/transcriptions")
    assert seen["auth"] == "Bearer sk-test"
    assert 'name="model"' in seen["body"] and "whisper-1" in seen["body"]


def test_remote_without_key_sends_no_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = OpenAiCompatHttpClient(
        url="https://selfhosted.example/v1", transport=transport)
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert seen["auth"] is None


def test_remote_base_url_wins_over_url():
    # base_url (adapter_kwargs) hat Vorrang vor der automatischen URL.
    client = OpenAiCompatHttpClient(
        url="http://crispr-qwen3:5094", base_url="https://api.mistral.ai/v1")
    assert client.url == "https://api.mistral.ai/v1"


def test_remote_http_error_raises():
    client = _client([httpx.Response(401, text="invalid api key")])
    with pytest.raises(Exception) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "401" in str(ei.value) or "invalid api key" in str(ei.value)


def test_remote_connect_error_has_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)

    transport = httpx.MockTransport(handler)
    client = OpenAiCompatHttpClient(url="https://api.openai.com/v1",
                                    transport=transport)
    with pytest.raises(RuntimeError) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "Remote-Backend" in str(ei.value)
    assert "base_url" in str(ei.value)


def test_remote_capabilities():
    c = OpenAiCompatHttpClient()
    assert c.capabilities.device == ["remote"]
    assert c.capabilities.word_timestamps is True
    assert c.capabilities.native_punctuation is True
