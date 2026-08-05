"""Env-Settings in der Admin-GUI (read-only, maskiert)."""
from __future__ import annotations

from app.routers import admin


def test_env_settings_lists_values(monkeypatch):
    class _S:
        POLYSCHNACK_DEFAULT_BACKEND = "ps-pk-onnx"
        POLYSCHNACK_PUNCTUATION_MODE = "off"
        POLYSCHNACK_DEFAULT_PUNCTUATION = False
        POLYSCHNACK_DEFAULT_LLM_ENHANCE = False
        POLYSCHNACK_ANON_RETENTION_MINUTES = 15
        POLYSCHNACK_ANON_MAX_DURATION_S = 300
        POLYSCHNACK_ANON_MAX_DISK_MB = 500
        POLYSCHNACK_ANON_MAX_UPLOAD_MB = 100
        POLYSCHNACK_MAX_QUEUE_LEN = 20
        POLYSCHNACK_LLM_URL = "https://llm.example.com/v1"
        POLYSCHNACK_LLM_API_KEY = "sk-super-secret"
        POLYSCHNACK_LLM_MODEL = "deepseek-chat"
        POLYSCHNACK_SMTP_HOST = "smtp.example.de"
        POLYSCHNACK_SMTP_PORT = 587
        POLYSCHNACK_SMTP_FROM = "asr@example.de"

    monkeypatch.setattr(admin, "settings", _S())
    out = admin.env_settings()
    names = {s["name"]: s for s in out["settings"]}
    assert names["default_backend"]["value"] == "ps-pk-onnx"
    assert names["anon_retention_minutes"]["value"] == "15"
    assert names["punctuation_mode"]["value"] == "off"
    assert names["llm_url"]["value"] == "https://llm.example.com/v1"


def test_env_settings_masks_secrets(monkeypatch):
    class _S:
        POLYSCHNACK_DEFAULT_BACKEND = "ps-pk-onnx"
        POLYSCHNACK_PUNCTUATION_MODE = "off"
        POLYSCHNACK_DEFAULT_PUNCTUATION = False
        POLYSCHNACK_DEFAULT_LLM_ENHANCE = False
        POLYSCHNACK_ANON_RETENTION_MINUTES = 15
        POLYSCHNACK_ANON_MAX_DURATION_S = 300
        POLYSCHNACK_ANON_MAX_DISK_MB = 500
        POLYSCHNACK_ANON_MAX_UPLOAD_MB = 100
        POLYSCHNACK_MAX_QUEUE_LEN = 20
        POLYSCHNACK_LLM_URL = ""
        POLYSCHNACK_LLM_API_KEY = "sk-super-secret"
        POLYSCHNACK_LLM_MODEL = "deepseek-chat"
        POLYSCHNACK_SMTP_HOST = ""
        POLYSCHNACK_SMTP_PORT = 587
        POLYSCHNACK_SMTP_FROM = ""

    monkeypatch.setattr(admin, "settings", _S())
    out = admin.env_settings()
    names = {s["name"]: s for s in out["settings"]}
    assert "sk-super-secret" not in str(out)
    assert names["llm_api_key"]["value"].startswith("•")


def test_env_settings_all_have_source_env(monkeypatch):
    class _S:
        POLYSCHNACK_DEFAULT_BACKEND = "ps-pk-onnx"
        POLYSCHNACK_PUNCTUATION_MODE = "off"
        POLYSCHNACK_DEFAULT_PUNCTUATION = False
        POLYSCHNACK_DEFAULT_LLM_ENHANCE = False
        POLYSCHNACK_ANON_RETENTION_MINUTES = 15
        POLYSCHNACK_ANON_MAX_DURATION_S = 300
        POLYSCHNACK_ANON_MAX_DISK_MB = 500
        POLYSCHNACK_ANON_MAX_UPLOAD_MB = 100
        POLYSCHNACK_MAX_QUEUE_LEN = 20
        POLYSCHNACK_LLM_URL = ""
        POLYSCHNACK_LLM_API_KEY = ""
        POLYSCHNACK_LLM_MODEL = "deepseek-chat"
        POLYSCHNACK_SMTP_HOST = ""
        POLYSCHNACK_SMTP_PORT = 587
        POLYSCHNACK_SMTP_FROM = ""

    monkeypatch.setattr(admin, "settings", _S())
    for s in admin.env_settings()["settings"]:
        assert s["source"] == "env"
