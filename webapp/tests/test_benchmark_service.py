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


# ── Auto-Ersatz (Reject → neues Sample aus CV-Pool) ───────────────────────

POOL = [
    {"path": "common_voice_de_40067184.mp3", "text": "Er steht in der Nachfolge Jean Fouquets, ohne dessen Meister zu sein.", "accent": "schweizerdeutsch", "age": "", "gender": ""},
    {"path": "common_voice_de_39565700.mp3", "text": "Das spezifische Epitheton bezieht sich auf die Blattform.", "accent": "österreichisches deutsch", "age": "", "gender": ""},
    {"path": "common_voice_de_37881293.mp3", "text": "Der Ruhpoldinger Abschnitt ist flächenmäßig am bedeutendsten.", "accent": "deutschland deutsch|fränkisch", "age": "", "gender": ""},
]


def test_replace_rejected_sample_finds_alternative(tmp_path: Path):
    svc = BenchmarkService(tmp_path / "benchmark_data")
    ersatz = svc.replace_rejected_sample(
        category="akzent", exclude_ids={"akzent_001"}, pool=POOL, seed=42
    )
    assert ersatz is not None
    assert ersatz["source_path"] in {s["path"] for s in POOL}  # aus Pool
    assert ersatz["id"].startswith("akzent_")
    assert ersatz["status"] == "active"
    assert ersatz["category"] == "akzent"


def test_replace_rejected_excludes_used_paths(tmp_path: Path):
    svc = BenchmarkService(tmp_path / "benchmark_data")
    ersatz = svc.replace_rejected_sample(
        category="akzent",
        exclude_ids=set(),
        used_paths={s["path"] for s in POOL},  # alle Pfade verbraucht
        pool=POOL, seed=42,
    )
    assert ersatz is None


def test_replace_rejected_new_id_avoids_collision(tmp_path: Path):
    svc = BenchmarkService(tmp_path / "benchmark_data")
    ersatz = svc.replace_rejected_sample(
        category="akzent", exclude_ids={"akzent_001"}, pool=POOL, seed=42
    )
    assert ersatz["id"] not in {"akzent_001"}


def test_create_version_after_reject(data_dir: Path):
    svc = BenchmarkService(data_dir)
    m2 = svc.create_version_after_reject(
        "akzent_001",
        {
            "id": "akzent_004",
            "category": "akzent",
            "source_path": "common_voice_de_40067184.mp3",
            "text": "Er steht in der Nachfolge Jean Fouquets.",
            "accent": "schweizerdeutsch",
            "age": "",
            "held_out": False,
            "status": "active",
        },
    )
    assert m2["version"] == 2
    assert m2["supersedes"] == 1
    by_id = {s["id"]: s for s in m2["samples"]}
    assert by_id["akzent_001"]["status"] == "rejected"
    assert by_id["akzent_004"]["status"] == "active"
    # v1 bleibt unverändert (immutable)
    m1 = svc._load_manifest(1)
    assert m1["samples"][0]["status"] == "active"


def test_create_version_after_reject_unknown_raises(data_dir: Path):
    svc = BenchmarkService(data_dir)
    with pytest.raises(KeyError):
        svc.create_version_after_reject("gibtsnicht", {"id": "x"})


def test_edit_sample_mutates_in_place(data_dir: Path):
    svc = BenchmarkService(data_dir)
    s = svc.edit_sample("akzent_001", text="Neuer Referenztext.")
    assert s["text"] == "Neuer Referenztext."
    m = svc.latest_manifest()
    assert m["samples"][0]["text"] == "Neuer Referenztext."
    assert m.get("updated_at")


def test_edit_sample_rejects_status_change(data_dir: Path):
    svc = BenchmarkService(data_dir)
    with pytest.raises(ValueError):
        svc.edit_sample("akzent_001", status="rejected")
