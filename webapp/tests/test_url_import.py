"""POST /api/recordings/from-url — URL-Import via yt-dlp.

Regression: `--print filename` lieferte den Download-Namen VOR der
Audio-Extraktion (z.B. .mp4) bzw. unterdrückte die Extraktion ganz → im
tmpdir lag keine WAV → 400 "yt-dlp produced no audio file" OHNE Log-Warnung.
Fix: `-f ba/b` (nur Audio) + WAV-Erkennung per glob statt stdout.

Fehlerpfade (alle ohne yt-dlp-Aufruf, subprocess.run gemockt):
- returncode != 0        → 400 "yt-dlp failed: ..."   (+ log.warning)
- TimeoutExpired         → 400 "URL download timed out (10 min)"
- FileNotFoundError      → 500 "yt-dlp not installed"
- keine WAV im tmpdir    → 400 "yt-dlp produced no audio file"
- leere URL              → 400 "no URL provided"
- leere WAV-Datei        → 400 "empty audio downloaded"
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module

    eng = create_engine(f"sqlite:///{tmp_path / 'urlimport.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.db import init_db

    init_db()  # _auto_migrate
    return eng


@pytest.fixture()
def client(db, monkeypatch, tmp_path):
    from app import deps
    from app.config import settings
    from app.identity import Identity, User  # noqa: F401
    from app.main import app
    import app.identity as identity_mod

    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")

    def _fake_identity(request, session):
        return Identity(User(id=1, sub="owner", kind="oidc"), None)

    monkeypatch.setattr(deps, "current_identity", _fake_identity)
    monkeypatch.setattr(identity_mod, "current_identity", _fake_identity)

    from sqlmodel import Session

    with Session(db) as s:
        s.add(User(id=1, sub="owner", kind="oidc"))
        s.commit()

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def patch_ytdlp(monkeypatch):
    """Mockt subprocess.run im url_import-Modul (echte WAV im Tmpdir).

    Nur yt-dlp-Aufrufe (erkennbar an `-o`) werden simuliert. Die
    ffmpeg-Konvertierung (_convert_to_wav_if_needed) wird durch einen
    pure-Python-Fake ersetzt — der CI-Test-Container hat KEIN ffmpeg.
    """
    import app.routers.url_import as url_import_mod

    url_import_mod._last_args = []

    def fake_run(args, **kwargs):
        if "-o" not in args:
            raise AssertionError(f"unerwarteter subprocess-Aufruf ohne -o: {args}")
        url_import_mod._last_args = args
        out_idx = args.index("-o")
        tmpdir = Path(args[out_idx + 1]).parent
        if _simulate["v"] == "timeout":
            raise subprocess.TimeoutExpired(args[0], 600)
        if _simulate["v"] == "notfound":
            raise FileNotFoundError("yt-dlp")
        if _wav["v"] is not None:
            (tmpdir / _wav_name["v"]).write_bytes(_wav["v"])
        r = _Result()
        r.tmpdir = tmpdir
        r.stdout = _stdout["v"]
        r.stderr = _stderr["v"]
        r.returncode = _rc["v"]
        return r

    monkeypatch.setattr(url_import_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(url_import_mod, "_convert_to_wav_if_needed", _fake_convert)
    return url_import_mod


def _fake_convert(raw: bytes, original_name: str):
    """Ersatz für _convert_to_wav_if_needed OHNE ffmpeg: schreibt die
    Quelle als 16-kHz-mono-16-bit-WAV (gleiche Dauer) zurück."""
    import io
    import wave

    with wave.open(io.BytesIO(raw), "rb") as src:
        dur = src.getnframes() / max(1, src.getframerate())

    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * int(dur * 16000))
    return buf.getvalue(), ".wav", "(konvertiert)"


class _Result:
    stdout = ""
    stderr = ""
    returncode = 0
    tmpdir: Path | None = None


def _make_wav_1s_16khz_mono() -> bytes:
    """Gültige WAV: 1 s @ 16 kHz mono 16-bit = 32000 Bytes Daten."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


def _make_wav_44k1_stereo() -> bytes:
    """Realistischer yt-dlp-Output: 1 s @ 44.1 kHz Stereo 16-bit."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00\x00\x00" * 44100)
    return buf.getvalue()


_stdout = {"v": ""}
_stderr = {"v": ""}
_rc = {"v": 0}
_wav = {"v": _make_wav_1s_16khz_mono()}
_wav_name = {"v": "audio.wav"}
_simulate = {"v": None}


@pytest.fixture(autouse=True)
def _reset_mock():
    _stdout["v"] = ""
    _stderr["v"] = ""
    _rc["v"] = 0
    _wav["v"] = _make_wav_1s_16khz_mono()  # gültige WAV, kein Null-Byte-Haufen
    _wav_name["v"] = "audio.wav"
    _simulate["v"] = None
    yield


def _post(client, url="https://example.com/audio.mp3"):
    return client.post("/api/recordings/from-url", data={"url": url})


# ── Happy Path ────────────────────────────────────────────────────────


def test_from_url_erfolg_legt_recording_an(client, patch_ytdlp):
    res = _post(client)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["original_name"].startswith("URL: ")
    assert body["mime"] == "audio/wav"
    assert 31000 < body["size_bytes"] < 33000  # 1 s @ 16 kHz mono 16-bit
    assert body["user_id"] == 1


def test_from_url_regression_stdout_zeigt_mp4_statt_wav(client, patch_ytdlp):
    """Kern-Regression: stdout sagt .mp4 (altes --print-Verhalten),
    aber die WAV existiert im tmpdir → Endpoint MUSS 201 liefern und
    die echte WAV verarbeiten (nicht den stdout-Namen)."""
    _stdout["v"] = "/tmp/xyz/audio.mp4\n"
    _wav_name["v"] = "audio.wav"
    res = _post(client)
    assert res.status_code == 201, res.text
    assert res.json()["mime"] == "audio/wav"
    assert 31000 < res.json()["size_bytes"] < 33000


def test_from_url_kein_print_kein_stdout_aber_wav(client, patch_ytdlp):
    """Ohne --print ist stdout leer; die WAV-Erkennung läuft per glob."""
    _stdout["v"] = ""
    res = _post(client)
    assert res.status_code == 201, res.text


def test_from_url_konvertiert_auf_16khz_mono(client, patch_ytdlp, tmp_path):
    """Corrupt-audio-Fix: yt-dlp liefert 44.1/48 kHz (Stereo) — die
    gespeicherte Datei MUSS 16 kHz mono sein (ASR/Peaks/WaveSurfer)."""
    import wave

    _wav["v"] = _make_wav_44k1_stereo()  # realistischer yt-dlp-Output
    res = _post(client)
    assert res.status_code == 201, res.text

    audio_dir = tmp_path / "audio"
    stored = sorted(audio_dir.glob("*.wav"))
    assert len(stored) == 1
    with wave.open(str(stored[0]), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


def test_from_url_ytdlp_erzeugt_keine_wav_400(client, patch_ytdlp):
    """Der Produktionsbug: yt-dlp lädt zwar, aber es entsteht keine WAV
    (--print unterdrückte die Extraktion) → 400 OHNE yt-dlp-Log."""
    _wav["v"] = None
    res = _post(client)
    assert res.status_code == 400
    assert "produced no audio file" in res.json()["detail"]


def test_from_url_leere_wav_400(client, patch_ytdlp):
    _wav["v"] = b""
    res = _post(client)
    assert res.status_code == 400
    assert "empty audio downloaded" in res.json()["detail"]


def test_from_url_leere_url_400(client, patch_ytdlp):
    res = _post(client, url="   ")
    assert res.status_code == 400
    assert "no URL provided" in res.json()["detail"]


# ── Fehlerpfade ───────────────────────────────────────────────────────


def test_from_url_ytdlp_failed_400_mit_warnung(client, patch_ytdlp, caplog):
    import logging

    _rc["v"] = 1
    _stderr["v"] = "ERROR: Unsupported URL"
    _wav["v"] = None
    with caplog.at_level(logging.WARNING, logger="app.routers.url_import"):
        res = _post(client)
    assert res.status_code == 400
    assert "yt-dlp failed" in res.json()["detail"]
    assert "yt-dlp failed for url=" in caplog.text


def test_from_url_timeout_400(client, patch_ytdlp):
    _simulate["v"] = "timeout"
    res = _post(client)
    assert res.status_code == 400
    assert "timed out" in res.json()["detail"]


def test_from_url_ytdlp_fehlend_500(client, patch_ytdlp):
    _simulate["v"] = "notfound"
    res = _post(client)
    assert res.status_code == 500
    assert "not installed" in res.json()["detail"]


# ── Flags & Dedup ─────────────────────────────────────────────────────


def test_from_url_uebergibt_enable_flags(client, patch_ytdlp):
    _post(client)
    # subprocess-Aufruf enthält -f ba/b und --audio-format wav
    args = patch_ytdlp._last_args
    assert "-f" in args and args[args.index("-f") + 1] == "ba/b"
    assert "--audio-format" in args and args[args.index("--audio-format") + 1] == "wav"
    assert "--no-playlist" in args
    assert "--print" not in args


def test_from_url_dedup_gleicher_content(client, patch_ytdlp):
    r1 = _post(client)
    r2 = _post(client)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # gleicher content_hash
