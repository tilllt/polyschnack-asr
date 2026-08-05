"""crispr-pk-cpp (CrispASR parakeet) HTTP-Adapter: eigener Container, eigene URL.

Weg-1-Umbau: pk-cpp läuft auf unserem eigenen hybriden CrispASR-Image
(pk-asr-cpp/) statt auf dem externen mudler/parakeet.cpp-server. Der
Adapter spricht denselben OpenAI-kompatiblen Endpunkt an, aber mit
eigener URL (CPP_URL, Default http://crispr-pk-cpp:5093) — NICHT
settings.ASR_URL (das ist der ONNX-ps-pk-onnx-Container).
"""
import httpx
import pytest

from app.asr_client.adapters.pk_cpp import PkCppClient


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


def _client(responses, url="http://crispr-pk-cpp:5093"):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses.pop(0)
        if isinstance(resp, httpx.Response):
            return resp
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    return PkCppClient(url=url, transport=transport)


def test_pk_cpp_transcribe_parses_segments():
    client = _client([_verbose_json()])
    result = client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Guten Tag"
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text"] == "Guten Tag"
    assert result["duration"] == 4.0
    assert result["language"] == "de"


def test_pk_cpp_posts_to_own_container_url_not_asr_url():
    """Bugfix: crispr-pk-cpp darf NICHT auf settings.ASR_URL (ONNX-Container)
    zeigen, sondern auf den eigenen cpp-Container."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = PkCppClient(url="http://crispr-pk-cpp:5093", transport=transport)
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert seen["url"].startswith("http://crispr-pk-cpp:5093")
    assert "/v1/audio/transcriptions" in seen["url"]


def test_pk_cpp_default_url_is_cpp_container():
    c = PkCppClient()
    assert c.url == "http://crispr-pk-cpp:5093"


def test_pk_cpp_connect_error_gives_hint():
    transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom")))
    client = PkCppClient(url="http://crispr-pk-cpp:5093", transport=transport)
    with pytest.raises(RuntimeError) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "crispr-pk-cpp" in str(ei.value)
    assert "crispr-pk-cpp" in str(ei.value)


def test_pk_cpp_capabilities_native_punctuation():
    c = PkCppClient()
    assert c.capabilities.label == "crispr-pk-cpp"
    assert c.capabilities.word_timestamps is True
    assert c.capabilities.native_punctuation is True
