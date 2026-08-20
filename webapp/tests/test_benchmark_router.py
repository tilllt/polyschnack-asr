"""Tests für die Benchmark-Routen (öffentliche GETs + Admin-POSTs)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# Import-Seiteneffekt in app/routers/models.py: _MODEL_CACHE.mkdir(DATA_DIR/models)
# — DATA_DIR MUSS vor dem App-Import gesetzt sein, sonst PermissionError auf /data.
_tmp = tempfile.mkdtemp(prefix="benchmark_test_")
os.environ.setdefault("DATA_DIR", _tmp)

from fastapi.testclient import TestClient  # noqa: E402

from app.benchmark_service import BenchmarkService  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

MANIFEST = {
    "version": 1,
    "created_at": "2026-08-04T12:00:00Z",
    "created_by": "admin",
    "supersedes": None,
    "categories": [
        {"id": "akzent", "name": "Akzente", "description": "Regionale Färbungen",
         "kanal": "clean", "inhalt": "akzent"},
        {"id": "jugend", "name": "Jugendstimmen", "description": "Teens-Sprecher",
         "kanal": "clean", "inhalt": "allgemein"},
    ],
    "axes": {
        "kanal": {
            "beschreibung": "Akustische Umgebung — wie klingt die Aufnahme?",
            "kategorien": {
                "clean": {"name": "Clean / Studio"},
                "telefon": {"name": "Telefon"},
            },
        },
        "inhalt": {
            "beschreibung": "Sprech-Inhalt — was wird gesprochen?",
            "kategorien": {
                "allgemein": {"name": "Allgemein"},
                "akzent": {"name": "Akzente"},
            },
        },
    },
    "samples": [
        {
            "id": "akzent_001",
            "category": "akzent",
            "kanal": "clean",
            "inhalt": "akzent",
            "source_path": "common_voice_de_18989125.mp3",
            "text": "Kisten und Möbel hingegen lassen sich nicht stopfen.",
            "accent": "schweizerdeutsch",
            "age": "teens",
            "held_out": False,
            "status": "active",
        },
        {
            "id": "akzent_002",
            "category": "akzent",
            "kanal": "clean",
            "inhalt": "akzent",
            "source_path": "common_voice_de_20255045.mp3",
            "text": "Diese Einspielung wurde in der Neuen Zeitschrift aufgenommen.",
            "accent": "schweizerdeutsch",
            "age": "sixties",
            "held_out": True,  # held-out → nicht öffentlich
            "status": "active",
        },
        {
            "id": "jugend_001",
            "category": "jugend",
            "kanal": "clean",
            "inhalt": "allgemein",
            "source_path": "common_voice_de_18208942.mp3",
            "text": "Wie viel wiegst du?",
            "accent": "",
            "age": "teens",
            "held_out": False,
            "status": "active",
        },
    ],
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """TestClient mit temporärem benchmark_data + WAV-Fixtures."""
    from app import db as db_module
    from sqlmodel import SQLModel, create_engine

    eng = create_engine(f"sqlite:///{tmp_path / 'benchmark.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)

    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    audio = v1 / "audio"
    audio.mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    # Kleine gültige WAV-Fixtures (44-Byte-Header + Stille)
    for sid in ("akzent_001", "akzent_002", "jugend_001"):
        wav = _miniwav()
        (audio / f"{sid}.wav").write_bytes(wav)
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(
        json.dumps({"version": 1, "rows": [{"backend": "ps-pk-onnx", "wer": 0.05}]})
    )
    (root / "pricing.json").write_text(
        json.dumps({"selfhost": {"ps-pk-onnx": {"eur_per_min": 0.01, "markup_x": 2.0}}})
    )
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "benchmark.db")
    monkeypatch.setattr(settings, "BENCHMARK_DATA_DIR", root)
    with TestClient(app) as c:
        yield c


def _miniwav() -> bytes:
    """Minimales WAV: 44-Byte-Header + 400 Samples Stille (16-bit mono 16k)."""
    import struct
    n = 400
    data = b"\x00\x00" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


# ── Öffentliche GETs ──────────────────────────────────────────────────────


def test_meta_public(client):
    r = client.get("/api/benchmark/meta")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert data["sample_count"] == 2  # akzent_001 + jugend_001 (ohne held-out)
    assert data["per_category"] == {"akzent": 1, "jugend": 1}


def test_meta_liefert_achsen_und_matrix(client):
    """2-Achsen-Matrix: axes (kanal/inhalt) + matrix-Zählung für die GUI."""
    r = client.get("/api/benchmark/meta")
    data = r.json()
    assert "axes" in data
    assert set(data["axes"].keys()) == {"kanal", "inhalt"}
    assert "clean" in data["axes"]["kanal"]["kategorien"]
    # Matrix: {kanal: {inhalt: count}} — nur öffentliche Samples
    m = data["matrix"]
    assert m["clean"]["akzent"] == 1
    assert m["clean"]["allgemein"] == 1
    # akzent_002 ist held-out → zählt nicht
    assert data["matrix_total"] == 2


def test_samples_exclude_held_out(client):
    r = client.get("/api/benchmark/samples")
    assert r.status_code == 200
    samples = r.json()["samples"]
    assert len(samples) == 2
    ids = {s["id"] for s in samples}
    assert "akzent_002" not in ids  # held-out
    assert all("preview_url" in s and "audio_url" in s for s in samples)


def test_samples_include_kanal_inhalt(client):
    """Change 042: kanal/inhalt müssen im Samples-Response sein, sonst
    findet der Matrix-Filter der UI (clean×akzente) keine Samples."""
    r = client.get("/api/benchmark/samples")
    assert r.status_code == 200
    samples = r.json()["samples"]
    assert all("kanal" in s and "inhalt" in s for s in samples)
    akzent = [s for s in samples if s["inhalt"] == "akzent"]
    assert len(akzent) == 1
    assert akzent[0]["kanal"] == "clean"
    assert akzent[0]["id"] == "akzent_001"


def test_audio_returns_wav_with_range(client):
    r = client.get("/api/benchmark/audio/akzent_001", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers.get("content-type", "").startswith("audio/wav")
    assert len(r.content) <= 100


def test_audio_full(client):
    r = client.get("/api/benchmark/audio/akzent_001")
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"


def test_audio_unknown_404(client):
    assert client.get("/api/benchmark/audio/nope").status_code == 404


def test_preview_returns_mp3(client):
    """Preview on-demand: aus WAV via ffmpeg → MP3 128k."""
    r = client.get("/api/benchmark/preview/jugend_001")
    if r.status_code == 404:
        pytest.skip("ffmpeg nicht verfügbar")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/mpeg")


def test_results_public(client):
    r = client.get("/api/benchmark/results")
    assert r.status_code == 200
    assert r.json()["rows"][0]["backend"] == "ps-pk-onnx"


def test_pricing_public(client):
    r = client.get("/api/benchmark/pricing")
    assert r.status_code == 200
    assert r.json()["selfhost"]["ps-pk-onnx"]["eur_per_min"] == 0.01


def test_versions_public(client):
    r = client.get("/api/benchmark/versions")
    assert r.status_code == 200
    assert r.json()["versions"][0]["version"] == 1
    assert r.json()["versions"][0]["active"] == 3


# ── Admin-POSTs ───────────────────────────────────────────────────────────


def test_reject_requires_admin(client):
    r = client.post("/api/benchmark/samples/akzent_001/reject")
    assert r.status_code in (401, 403)


def test_edit_requires_admin(client):
    r = client.post("/api/benchmark/samples/akzent_001/edit", json={"text": "x"})
    assert r.status_code in (401, 403)
