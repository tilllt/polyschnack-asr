"""Tests für den LLM-Call (Task D1) — httpx gemockt."""
from __future__ import annotations

import httpx
import pytest

from app import llm
from app.config import settings


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_LLM_URL", "https://llm.example.com/v1")
    monkeypatch.setattr(settings, "POLYSCHNACK_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "POLYSCHNACK_LLM_MODEL", "deepseek-chat")


def test_chat_sends_openai_compatible_request(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "Antwort"}}]
        })

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.chat("System", "User text")
    assert out == "Antwort"
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["json"]["messages"][0]["content"] == "System"
    assert captured["json"]["messages"][1]["content"] == "User text"


def test_chat_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_LLM_API_KEY", "")
    with pytest.raises(RuntimeError, match="API_KEY"):
        llm.chat("S", "U")


def test_chat_without_url_raises(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_LLM_URL", "")
    with pytest.raises(RuntimeError, match="URL"):
        llm.chat("S", "U")


def test_chat_error_raises_with_message(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(500, text="server error")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        llm.chat("S", "U")
