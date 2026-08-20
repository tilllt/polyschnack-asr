"""Change 043: Tor-Fallback-Unit-Tests (letzte Stufe der Download-Kaskade).

Getestet werden die gekapselten Bausteine OHNE echten Tor-Container:

- _is_bot_block: Bot-Schutz-Signaturen (case-insensitive) vs. normale Fehler
- _tor_rate_limit_allowed / _tor_record_usage: Rolling-Window-Rate-Limit
  (Pflicht aus User-Entscheidung „Polyschnack muss rate-limiting einbauen")
- _tor_lock: loop-keyed Lock (asyncio.Lock ist an den Event-Loop gebunden;
  Tests mit asyncio.run erzeugen je einen neuen Loop)
- _tor_fallback_download: Kaskade mit gemocktem Docker-Proxy + yt-dlp
  (deaktiviert → 400; Rate-Limit → 429 + Retry-After; Container fehlt → 503;
  Erfolg → usage recordet; alle Circuits fehl → 400 mit restart je Circuit)
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import docker_proxy  # noqa: E402
from app.config import settings  # noqa: E402
from app.routers import url_import  # noqa: E402
from app.routers.url_import import (  # noqa: E402
    _TOR_CONTAINER,
    _is_bot_block,
    _tor_fallback_download,
    _tor_lock,
    _tor_rate_limit_allowed,
    _tor_record_usage,
    _tor_usage,
)


@pytest.fixture(autouse=True)
def clean_tor_state():
    """In-Memory-Store zwischen Tests leeren (rolling window ist prozessweit)."""
    _tor_usage.clear()
    yield
    _tor_usage.clear()


@pytest.fixture()
def tor_settings(monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_FALLBACK", True)
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_MAX_PER_HOUR", 2)
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_MAX_CIRCUITS", 3)
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_MAX_SIZE_MB", 500)
    return settings


# ── _is_bot_block ──────────────────────────────────────────────────────


def test_bot_block_erkennt_signaturen():
    for sig in (
        "Sign in to confirm you're not a bot",
        "ERROR: [youtube] abcd: HTTP Error 403: Forbidden",
        "HTTP Error 400: Bad Request",
        "nsig extraction failed:",
        "confirm you're not a bot",
        "requested format is not available",
    ):
        assert _is_bot_block(sig), f"Signatur nicht erkannt: {sig}"


def test_bot_block_case_insensitive():
    assert _is_bot_block("HTTP ERROR 403: FORBIDDEN")
    assert _is_bot_block("SIGN IN TO CONFIRM")


def test_bot_block_ignoriert_normale_fehler():
    for msg in (
        "ERROR: [youtube] Video unavailable",
        "ERROR: Unable to download webpage: <urlopen error timed out>",
        "network unreachable",
        "",
    ):
        assert not _is_bot_block(msg), f"falsch positiv: {msg}"
    assert not _is_bot_block(None)  # type: ignore[arg-type]  # None → False, kein Crash


# ── Rate-Limit (rolling window) ────────────────────────────────────────


def test_rate_limit_deaktiviert_bei_limit_0(tor_settings, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_MAX_PER_HOUR", 0)
    allowed, retry = _tor_rate_limit_allowed("u1", now=1000.0)
    assert allowed is True
    assert retry == 0


def test_rate_limit_unter_limit_erlaubt(tor_settings):
    _tor_usage["u1"] = [100.0]
    allowed, retry = _tor_rate_limit_allowed("u1", now=200.0)
    assert allowed is True
    assert retry == 0


def test_rate_limit_am_limit_blockiert(tor_settings):
    _tor_usage["u1"] = [100.0, 150.0]
    allowed, retry = _tor_rate_limit_allowed("u1", now=200.0)
    assert allowed is False
    assert retry > 0


def test_rate_limit_rolling_window_verfällt(tor_settings):
    # Slot vor > 1 h zählt nicht mehr (rolling window 3600 s).
    _tor_usage["u1"] = [100.0, 200.0]
    allowed, _ = _tor_rate_limit_allowed("u1", now=100.0 + 3600.0 + 1.0)
    assert allowed is True
    # 2 frische Slots (beide < 1 h alt) → Limit erreicht
    _tor_usage["u1"] = [3400.0, 3700.0]
    allowed, _ = _tor_rate_limit_allowed("u1", now=3700.0)
    assert allowed is False


def test_rate_limit_retry_after_korrekt(tor_settings):
    # ältester Slot 1800 s her → noch 1800 s bis zum Ablauf
    _tor_usage["u1"] = [1900.0, 2000.0]
    allowed, retry = _tor_rate_limit_allowed("u1", now=3700.0)
    assert allowed is False
    assert retry == 1800


def test_record_usage_füllt_und_blockiert(tor_settings):
    _tor_record_usage("u1")
    assert _tor_rate_limit_allowed("u1")[0] is True
    _tor_record_usage("u1")
    assert _tor_rate_limit_allowed("u1")[0] is False  # Limit 2 erreicht


def test_record_usage_entfernt_alte_slots(tor_settings, monkeypatch):
    monkeypatch.setattr(url_import.time, "time", lambda: 4000.0)
    _tor_usage["u1"] = [100.0]  # alt
    _tor_record_usage("u1")
    assert _tor_usage["u1"] == [4000.0]


# ── Loop-keyed Lock ────────────────────────────────────────────────────


def test_tor_lock_gleicher_loop_gleiche_instanz():
    async def inner():
        a = _tor_lock()
        b = _tor_lock()
        return a is b

    assert asyncio.run(inner()) is True


def test_tor_lock_verschiedene_loops_getrennt():
    # Motivation: Tests (asyncio.run) erzeugen je einen neuen Event-Loop —
    # ein an den ersten Loop gebundenes Lock würde beim zweiten Aufruf mit
    # RuntimeError crashen. Wichtig ist also: KEIN Crash, nicht id-Unterschied
    # (id() ist über GC hinweg instabil — asyncio.run kann die Speicheradresse
    # des alten Loops wiederverwenden).
    async def use_lock():
        lock = _tor_lock()
        async with lock:
            return True

    assert asyncio.run(use_lock()) is True
    assert asyncio.run(use_lock()) is True  # zweiter Loop: kein RuntimeError


# ── _tor_fallback_download (Kaskade) ───────────────────────────────────


class FakeProxy:
    """Minimaler DockerProxyClient-Ersatz für die Kaskaden-Tests."""

    def __init__(self, state=None, restart_error=None):
        # state=None bedeutet „Container existiert nicht" — bewusst KEIN
        # Default-Ersatz (sonst greift der 503-Pfad nie).
        self.state = state
        self.started = False
        self.restart_calls = 0
        self.restart_error = restart_error

    def container_state(self, name):
        return self.state

    def start(self, name):
        self.started = True
        # On-demand-Start: Container wird danach als running/healthy gemeldet.
        if self.state is not None:
            self.state = dict(self.state, running=True, health="healthy")

    def restart(self, name):
        self.restart_calls += 1
        if self.restart_error:
            raise self.restart_error


def fake_proc(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_fallback_deaktiviert(tor_settings, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_TOR_FALLBACK", False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_tor_fallback_download("https://x.example/v", "/tmp/out", "u1"))
    assert ei.value.status_code == 400


def test_fallback_rate_limit_429(tor_settings, monkeypatch):
    # Frische Slots in der echten Zeit (now=None → time.time() im Check)
    now = __import__("time").time()
    _tor_usage["u1"] = [now - 100.0, now - 50.0]
    monkeypatch.setattr(url_import, "get_docker_client", lambda: FakeProxy(state={"running": True, "health": "healthy"}))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
        )
    assert ei.value.status_code == 429
    assert ei.value.headers["Retry-After"]  # Retry-After gesetzt


def test_fallback_container_fehlt_503(tor_settings, monkeypatch):
    monkeypatch.setattr(url_import, "get_docker_client", lambda: FakeProxy(state=None))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
        )
    assert ei.value.status_code == 503
    assert "ps-tor" in ei.value.detail


def test_fallback_startet_container_bei_stop(tor_settings, monkeypatch):
    proxy = FakeProxy(state={"running": False, "health": None})
    monkeypatch.setattr(url_import, "get_docker_client", lambda: proxy)
    monkeypatch.setattr(
        url_import, "_run_ytdlp_proxy", lambda *a, **k: fake_proc(0)
    )
    proc = asyncio.run(
        _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
    )
    assert proxy.started is True
    assert proc.returncode == 0


def test_fallback_erfolg_recordet_usage(tor_settings, monkeypatch):
    monkeypatch.setattr(url_import, "get_docker_client", lambda: FakeProxy(state={"running": True, "health": "healthy"}))
    monkeypatch.setattr(
        url_import, "_run_ytdlp_proxy", lambda *a, **k: fake_proc(0)
    )
    proc = asyncio.run(
        _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
    )
    assert proc.returncode == 0
    assert len(_tor_usage["u1"]) == 1  # Slot vermerkt


def test_fallback_alle_circuits_fail_400_mit_restart(tor_settings, monkeypatch):
    proxy = FakeProxy(state={"running": True, "health": "healthy"})
    monkeypatch.setattr(url_import, "get_docker_client", lambda: proxy)
    monkeypatch.setattr(
        url_import,
        "_run_ytdlp_proxy",
        lambda *a, **k: fake_proc(1, "ERROR: exit node refused"),
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
        )
    assert ei.value.status_code == 400
    assert "Alle Tor-Circuits fehlgeschlagen" in ei.value.detail
    # Neuer Circuit je Versuch nach dem ersten: MAX_CIRCUITS-1 Restarts
    assert proxy.restart_calls == settings.POLYSCHNACK_TOR_MAX_CIRCUITS - 1


def test_fallback_restart_fehler_bricht_nicht_ab(tor_settings, monkeypatch):
    proxy = FakeProxy(
        state={"running": True, "health": "healthy"},
        restart_error=docker_proxy.DockerProxyError("boom"),
    )
    monkeypatch.setattr(url_import, "get_docker_client", lambda: proxy)
    monkeypatch.setattr(
        url_import,
        "_run_ytdlp_proxy",
        lambda *a, **k: fake_proc(1, "ERROR: refused"),
    )
    with pytest.raises(HTTPException):
        asyncio.run(
            _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
        )
    # Log.warning statt Abbruch — nächster Circuit wird trotzdem versucht
    assert proxy.restart_calls == settings.POLYSCHNACK_TOR_MAX_CIRCUITS - 1


def test_fallback_ytdlp_fehlt_500(tor_settings, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("yt-dlp")

    monkeypatch.setattr(url_import, "get_docker_client", lambda: FakeProxy(state={"running": True, "health": "healthy"}))
    monkeypatch.setattr(url_import, "_run_ytdlp_proxy", boom)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            _tor_fallback_download("https://x.example/v", "/tmp/out", "u1")
        )
    assert ei.value.status_code == 500
