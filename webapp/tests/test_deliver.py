"""Delivery (Task D5) — E-Mail + WebDAV, smtplib/httpx gemockt."""
from __future__ import annotations

import json

import httpx
import pytest

from app import deliver
from app.config import settings
from app.models import DeliveryTarget, Recording


def _rec():
    return Recording(id=1, uid="r1", original_name="meeting.mp3", stored_path="p",
                     text="Hallo Welt")


def _target(kind, config):
    return DeliveryTarget(id=1, user_id=1, name="t", kind=kind,
                          config=json.dumps(config))


@pytest.fixture(autouse=True)
def _smtp_cfg(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_HOST", "smtp.example.de")
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_PORT", 587)
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_USER", "user")
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_PASS", "pw")
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_FROM", "asr@example.de")


def test_email_sends_multipart(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, *a): sent["login"] = a
        def send_message(self, msg): sent["msg"] = msg

    monkeypatch.setattr(deliver.smtplib, "SMTP", FakeSMTP)
    deliver._deliver_email(_rec(), {"to": "a@b.de"})
    assert sent["login"] == ("user", "pw")
    assert sent["msg"]["To"] == "a@b.de"
    assert "meeting.mp3.txt" in str(sent["msg"])


def test_email_without_smtp_config_fails(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_SMTP_HOST", "")
    with pytest.raises(RuntimeError, match="SMTP"):
        deliver._deliver_email(_rec(), {"to": "a@b.de"})


def test_webdav_puts_file(monkeypatch):
    captured = {}

    def fake_put(url, auth=None, content=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        captured["content"] = content
        return httpx.Response(201, request=httpx.Request("PUT", url))

    monkeypatch.setattr(deliver.httpx, "put", fake_put)
    from app.crypto import encrypt

    deliver._deliver_webdav(_rec(), {
        "url": "https://dav.example/remote.php/dav/files/u",
        "username": "u", "password": encrypt("pw"), "path": "ziel",
    })
    assert captured["url"] == "https://dav.example/remote.php/dav/files/u/ziel/meeting.mp3.txt"
    assert captured["auth"] == ("u", "pw")
    assert captured["content"] == b"Hallo Welt"


def test_webdav_failure_raises(monkeypatch):
    def fake_put(url, auth=None, content=None, timeout=None):
        return httpx.Response(403, request=httpx.Request("PUT", url))

    monkeypatch.setattr(deliver.httpx, "put", fake_put)
    from app.crypto import encrypt

    with pytest.raises(httpx.HTTPStatusError):
        deliver._deliver_webdav(_rec(), {
            "url": "https://dav.example", "username": "u",
            "password": encrypt("pw"), "path": ""})


def test_deliver_unknown_kind_raises():
    t = _target("ftp", {})
    with pytest.raises(RuntimeError, match="unbekannt"):
        deliver.deliver(_rec(), t)
