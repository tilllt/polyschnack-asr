"""Tests für BenchmarkService (versionierte Manifeste + Sample-Verwaltung)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmark_service import BenchmarkService

MANIFEST_V1 = {
    "version": 1,
    "created_at": "2026-08-04T12:00:00Z",
    "created_by": "admin",
    "supersedes": None,
    "categories": [
        {"id": "akzent", "name": "Akzente", "description": "Regionale Färbungen"},
        {"id": "jugend", "name": "Jugendstimmen", "description": "Teens-Sprecher"},
        {"id": "clean", "name": "Hochdeutsch", "description": "Klare Standard-Sätze"},
    ],
    "samples": [
        {
            "id": "akzent_001",
            "category": "akzent",
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
            "source_path": "common_voice_de_20255045.mp3",
            "text": "Diese Einspielung wurde in der Neuen Zeitschrift aufgenommen.",
            "accent": "schweizerdeutsch",
            "age": "sixties",
            "held_out": True,
            "status": "active",
        },
        {
            "id": "akzent_003",
            "category": "akzent",
            "source_path": "common_voice_de_27021181.mp3",
            "text": "Auf dem Helm mit rot-silbernen Decken.",
            "accent": "polnisch deutsch",
            "age": "",
            "held_out": False,
            "status": "rejected",
        },
    ],
}


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """benchmark_data mit v1-Manifest + Audio-Fixtures."""
    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    audio = v1 / "audio"
    audio.mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST_V1, ensure_ascii=False))
    for s in MANIFEST_V1["samples"]:
        (audio / f"{s['id']}.wav").write_bytes(b"RIFFxxxxWAVEfmt " + s["id"].encode())
    return root


def test_load_manifest_latest_version(data_dir: Path):
    svc = BenchmarkService(data_dir)
    m = svc.latest_manifest()
    assert m["version"] == 1
    assert len(m["samples"]) == 3


def test_public_samples_exclude_held_out_and_rejected(data_dir: Path):
    svc = BenchmarkService(data_dir)
    public = svc.public_samples()
    assert len(public) == 1
    assert public[0]["id"] == "akzent_001"
    assert all(s["status"] == "active" and not s["held_out"] for s in public)


def test_categories_aus_manifest(data_dir: Path):
    svc = BenchmarkService(data_dir)
    cats = svc.categories()
    assert [c["id"] for c in cats] == ["akzent", "jugend", "clean"]


def test_sample_audio_path_exists(data_dir: Path):
    svc = BenchmarkService(data_dir)
    p = svc.sample_audio_path("akzent_001", kind="final")
    assert p.exists()
    assert p.suffix == ".wav"


def test_sample_audio_path_unknown_raises(data_dir: Path):
    svc = BenchmarkService(data_dir)
    with pytest.raises(KeyError):
        svc.sample_audio_path("gibtsnicht", kind="final")


def test_sample_audio_preview_mp3(data_dir: Path):
    """Preview-Pfad: vN/preview/{id}.mp3 (128k, wird on-demand erzeugt)."""
    svc = BenchmarkService(data_dir)
    p = svc.sample_audio_path("akzent_001", kind="preview")
    assert p.suffix == ".mp3"
    assert "preview" in str(p)
