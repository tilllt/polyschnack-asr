"""``language`` geht als OpenAI-konformes Formularfeld raus (Change 234).

Zwei Erwartungen je Adapter — beide an den ECHTEN HTTP-Adapter geprüft:
  * ``language="de"`` → Feld ``language`` steht im Multipart-Body,
  * ohne Angabe (AUTO) → Feld fehlt, der Request ist unverändert wie vorher.
"""
from __future__ import annotations

import httpx
import pytest

from app.asr_client.adapters.crisp_asr_http import CrispAsrHttpClient
from app.asr_client.adapters.openai_compat_http import OpenAiCompatHttpClient
from app.asr_client.adapters.pk_cpp import PkCppClient
from app.asr_client.adapters.pk_python import PkPythonClient
from app.asr_client.adapters.qwen3_asr_http import Qwen3AsrHttpClient

VERBOSE_JSON = {
    "task": "transcribe",
    "language": "de",
    "duration": 1.0,
    "text": "Hallo Welt",
    "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hallo Welt"}],
}

ADAPTER = [PkPythonClient, PkCppClient, Qwen3AsrHttpClient, CrispAsrHttpClient,
           OpenAiCompatHttpClient]


def _client(cls, seen: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode("utf-8", "replace")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=VERBOSE_JSON)

    kwargs = {"url": "http://backend:5092", "transport": httpx.MockTransport(handler)}
    if cls is OpenAiCompatHttpClient:
        kwargs["model"] = "whisper-1"
    return cls(**kwargs)


@pytest.mark.parametrize("cls", ADAPTER, ids=lambda c: c.__name__)
def test_language_landet_im_formular(cls):
    seen: dict = {}
    _client(cls, seen).transcribe(b"\x00\x01", "a.wav", "audio/wav", language="de")
    assert 'name="language"' in seen["body"], seen["body"][:400]
    assert "de" in seen["body"]


@pytest.mark.parametrize("cls", ADAPTER, ids=lambda c: c.__name__)
def test_auto_laesst_das_feld_weg(cls):
    seen: dict = {}
    _client(cls, seen).transcribe(b"\x00\x01", "a.wav", "audio/wav")
    assert 'name="language"' not in seen["body"], seen["body"][:400]


@pytest.mark.parametrize("cls", ADAPTER, ids=lambda c: c.__name__)
def test_noise_reduce_und_language_gleichzeitig(cls):
    """Regression: noise_reduce (vor language) bleibt übergebbar."""
    seen: dict = {}
    _client(cls, seen).transcribe(
        b"\x00\x01", "a.wav", "audio/wav", noise_reduce=False, language="de"
    )
    assert 'name="language"' in seen["body"]
