"""ps-pk-onnx (PkPythonClient) — HTTP-Adapter-Tests.

Dieselbe Teststruktur wie test_pk_cpp_adapter / test_qwen3_http_adapter /
test_crisp_http_adapter: MockTransport + verbose_json-Payloads. Damit sind
ALLE aktiven ASR-Backends über ihre Adapter getestet (Backend-Matrix siehe
test_all_asr_backends.py).
"""
import httpx
import pytest

from app.asr_client.adapters.pk_python import PkPythonClient


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


def _client(responses, url="http://ps-pk-onnx:5092", **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses.pop(0)
        if isinstance(resp, httpx.Response):
            return resp
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    return PkPythonClient(url=url, transport=transport, **kw)


def test_pk_python_transcribe_parses_segments():
    client = _client([_verbose_json()])
    result = client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Guten Tag"
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text"] == "Guten Tag"
    assert result["segments"][0]["words"][1]["word"] == "Tag"
    assert result["duration"] == 4.0
    assert result["language"] == "de"


def test_pk_python_posts_to_url_with_auth_and_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode(errors="ignore")
        return httpx.Response(200, json=_verbose_json())

    transport = httpx.MockTransport(handler)
    client = PkPythonClient(url="http://ps-pk-onnx:5092", api_key="sekret",
                            transport=transport)
    client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert seen["url"].startswith("http://ps-pk-onnx:5092")
    assert "/v1/audio/transcriptions" in seen["url"]
    assert seen["auth"] == "Bearer sekret"
    assert "verbose_json" in seen["body"]
    assert "timestamp_granularities" in seen["body"]


def test_pk_python_default_url_is_settings_asr_url():
    from app.config import settings
    c = PkPythonClient()
    assert c.url == settings.ASR_URL.rstrip("/")


def test_pk_python_connect_error_gives_hint():
    transport = httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom")))
    client = PkPythonClient(url="http://ps-pk-onnx:5092", transport=transport)
    with pytest.raises(RuntimeError) as ei:
        client.transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert "ps-pk-onnx" in str(ei.value)


def test_pk_python_streaming_parses_sse():
    events = [
        {"text": "Guten", "chunk_index": 0, "total_chunks": 2,
         "start": 0.0, "end": 1.0, "final": False},
        # final-Event trägt den VOLLEN Text (Server-Semantik), nicht das Delta
        {"text": "Guten Tag", "chunk_index": 1, "total_chunks": 2,
         "start": 1.0, "end": 2.0, "final": True},
    ]
    body = "".join(f"data: {__import__('json').dumps(e)}\n\n" for e in events)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body,
                              headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    client = PkPythonClient(url="http://ps-pk-onnx:5092", transport=transport)
    chunks: list = []

    def on_chunk(text, idx, total, start, end, final):
        chunks.append((text, idx, total, start, end, final))

    result = client.transcribe_streaming(
        b"\x00\x01", "a.wav", "audio/wav", on_chunk=on_chunk)
    assert result["text"] == "Guten Tag"
    assert len(chunks) == 2
    assert chunks[1][1] == 1 and chunks[1][2] == 2
    # SSE-Fehler-Events werden als RuntimeError propagiert:
    def err_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="data: {\"error\": \"kaputt\"}\n\n")
    err_client = PkPythonClient(
        url="http://ps-pk-onnx:5092",
        transport=httpx.MockTransport(err_handler))
    with pytest.raises(RuntimeError, match="kaputt"):
        err_client.transcribe_streaming(b"\x00\x01", "a.wav", "audio/wav")


def test_pk_python_async_job_polls_until_done(monkeypatch):
    monkeypatch.setattr("app.asr_client.adapters.pk_python.time.sleep",
                        lambda s: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "j1"})
        return httpx.Response(200, json={
            "status": "done", "progress_pct": 100, "text": "Guten Tag",
            "duration": 4.0, "language": "de",
            "segments": [{"start": 0.0, "end": 2.0, "text": "Guten Tag",
                          "words": [{"word": "Guten", "start": 0.0, "end": 1.0},
                                    {"word": "Tag", "start": 1.0, "end": 2.0}]}],
        })

    transport = httpx.MockTransport(handler)
    client = PkPythonClient(url="http://ps-pk-onnx:5092", transport=transport)
    result = client.transcribe_async(b"\x00\x01", "a.wav", "audio/wav")
    assert result["text"] == "Guten Tag"
    methods = [c[0] for c in calls]
    assert methods == ["POST", "GET"]
    assert "/v1/audio/transcriptions/async" in calls[0][1]
    assert "/v1/audio/jobs/j1" in calls[1][1]


def test_pk_python_async_job_failure_raises(monkeypatch):
    monkeypatch.setattr("app.asr_client.adapters.pk_python.time.sleep",
                        lambda s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "j2"})
        return httpx.Response(200, json={"status": "failed",
                                         "error": "model crashed"})

    transport = httpx.MockTransport(handler)
    client = PkPythonClient(url="http://ps-pk-onnx:5092", transport=transport)
    with pytest.raises(RuntimeError, match="model crashed"):
        client.transcribe_async(b"\x00\x01", "a.wav", "audio/wav")


def test_pk_python_capabilities():
    c = PkPythonClient()
    assert c.capabilities.label == "ps-pk-onnx"
    assert c.capabilities.word_timestamps is True
    assert c.capabilities.streaming is True
    assert c.capabilities.async_jobs is True
    assert c.capabilities.accepts_compressed is True
