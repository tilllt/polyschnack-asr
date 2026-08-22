"""Tests für die Benchmark-Routen (öffentliche GETs + Admin-POSTs)."""
from __future__ import annotations

import hashlib
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
    # VAD-Paket (Change 073): vad-manifest + Audio-WAVs
    vad = v1 / "vad"
    (vad / "audio").mkdir(parents=True)
    (vad / "vad-manifest.json").write_text(json.dumps({
        "version": 1,
        "testset_version": "v4-public",
        "samples": [
            {"id": "de_00_lead2", "source": "piper-tts", "variant": "lead2",
             "split": "public", "gt": [{"start": 0.0, "end": 0.2}]},
            {"id": "cv_clean_000", "source": "commonvoice:cv_clean_000",
             "variant": "snr0_n0", "split": "public", "gt": [{"start": 0.0, "end": 0.2}]},
            {"id": "noise_demand_DKITCHEN_16k_sample", "source": "demand",
             "variant": "demand", "split": "public", "gt": []},
        ],
    }, ensure_ascii=False))
    for sid in ("de_00_lead2", "cv_clean_000", "noise_demand_DKITCHEN_16k_sample"):
        (vad / "audio" / f"{sid}.wav").write_bytes(_miniwav())
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


# ── VAD-Testset-Samples (Change 073) ──────────────────────────────────────


def test_vadsamples_public(client):
    """VAD-Sample-Liste öffentlich: alle Paket-Samples mit URLs + GT-Flag."""
    r = client.get("/api/benchmark/vadsamples")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    ids = {s["id"] for s in data["samples"]}
    assert ids == {"de_00_lead2", "cv_clean_000", "noise_demand_DKITCHEN_16k_sample"}
    for s in data["samples"]:
        assert s["preview_url"].startswith("/api/benchmark/vadpreview/")
        assert s["audio_url"].startswith("/api/benchmark/vadaudio/")
    # GT-Flag: de_00_lead2 hat GT, noise_demand nicht
    by_id = {s["id"]: s for s in data["samples"]}
    assert by_id["de_00_lead2"]["has_gt"] is True
    assert by_id["noise_demand_DKITCHEN_16k_sample"]["has_gt"] is False
    assert by_id["de_00_lead2"]["source"] == "piper-tts"


def test_vadaudio_returns_wav(client):
    r = client.get("/api/benchmark/vadaudio/de_00_lead2")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/wav")


def test_vadaudio_unknown_404(client):
    assert client.get("/api/benchmark/vadaudio/nope").status_code == 404


def test_vadpreview_returns_mp3(client):
    """VAD-Preview on-demand: aus VAD-WAV via ffmpeg → MP3 128k."""
    r = client.get("/api/benchmark/vadpreview/de_00_lead2")
    if r.status_code == 404:
        pytest.skip("ffmpeg nicht verfügbar")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/mpeg")


def test_vadpreview_unknown_404(client):
    assert client.get("/api/benchmark/vadpreview/nope").status_code == 404


# ── Benchmark-Set-Auto-Update (Change 075) ───────────────────────────────


def test_sets_status_public(client):
    """Status öffentlich: Konfiguration + Versionen, aber kein voller SHA."""
    r = client.get("/api/benchmark/sets")
    assert r.status_code == 200
    data = r.json()
    assert data["mechanism"] == "benchmark-set"
    assert data["current_version"] == 1
    assert data["installed_versions"] == [1]
    assert "url" in data
    assert "sha_prefix" in data
    assert "last_error" in data


def test_sets_install_requires_admin(client):
    r = client.post("/api/benchmark/sets/install")
    assert r.status_code in (401, 403)


def _make_set_zip(version: int = 2, n_samples: int = 1, evil: bool = False) -> bytes:
    """Benchmark-Set-ZIP-Fixture: manifest.json + audio/preview-WAVs."""
    import io
    import struct
    import zipfile

    buf = io.BytesIO()
    wav = _miniwav()
    samples = [
        {"id": f"clean_{i:03d}", "category": "clean", "kanal": "clean",
         "inhalt": "allgemein", "text": f"Text {i}", "source_path": f"src_{i}.mp3",
         "accent": "", "age": "", "held_out": False, "status": "active"}
        for i in range(n_samples)
    ]
    manifest = {
        "version": version,
        "created_at": "2026-08-21T00:00:00Z",
        "created_by": "admin",
        "supersedes": None,
        "categories": [{"id": "clean", "name": "Hochdeutsch", "kanal": "clean",
                        "inhalt": "allgemein", "description": "Klare Sätze"}],
        "axes": {"kanal": {"beschreibung": "x", "kategorien": {"clean": {"name": "Clean"}}},
                 "inhalt": {"beschreibung": "x", "kategorien": {"allgemein": {"name": "Allgemein"}}}},
        "samples": samples,
    }
    with zipfile.ZipFile(buf, "w") as z:
        entries = [("manifest.json", json.dumps(manifest, ensure_ascii=False))]
        for i in range(n_samples):
            entries.append((f"audio/clean_{i:03d}.wav", wav))
            entries.append((f"preview/clean_{i:03d}.wav", wav))
        if evil:
            entries.append(("../../etc/passwd", "boom"))
        for name, data in entries:
            # Deterministische ZIPs: writestr() würde den aktuellen
            # Zeitstempel setzen (2-s-Granularität) → SHA-Vergleich in
            # test_install_via_git_uses_sha_file wird flaky (T7/083).
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, data)
    return buf.getvalue()


def test_sets_installer_happy_path(tmp_path, monkeypatch):
    """Installer: Download+Verifikation+Entpacken+aktivieren (v2 > v1)."""
    import urllib.request

    zdata = _make_set_zip(version=2, n_samples=2)
    sha = hashlib.sha256(zdata).hexdigest()

    class FakeResp:
        def read(self): return zdata
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=300: FakeResp())

    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    (v1 / "audio").mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    (v1 / "audio" / "akzent_001.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(json.dumps({"version": 1, "rows": []}))

    svc = BenchmarkService(root)
    res = svc.install_set_from_release(
        url="https://example.com/set.zip", expected_sha=sha
    )
    assert res["ok"] and not res["skipped"]
    assert res["installed_version"] == 2
    assert res["sample_count"] == 2
    assert res["supersedes"] == 1
    # v2 ist jetzt latest + Manifest supersedes gesetzt
    assert svc.latest_manifest()["version"] == 2
    assert svc.latest_manifest()["supersedes"] == 1
    # audio vorhanden
    assert (root / "versions" / "v2" / "audio" / "clean_000.wav").exists()
    # kein tmp-Rest
    assert not (root / "versions" / ".tmp-v2").exists()


def test_sets_installer_sha_mismatch(tmp_path, monkeypatch):
    """SHA-Mismatch: RuntimeError, KEIN Zustand geändert, kein tmp-Rest."""
    import urllib.request

    zdata = _make_set_zip(version=2)

    class FakeResp:
        def read(self): return zdata
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=300: FakeResp())

    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    (v1 / "audio").mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    (v1 / "audio" / "akzent_001.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(json.dumps({"version": 1, "rows": []}))

    svc = BenchmarkService(root)
    with pytest.raises(RuntimeError, match="SHA256-Mismatch"):
        svc.install_set_from_release(
            url="https://example.com/set.zip", expected_sha="0" * 64
        )
    assert svc.latest_manifest()["version"] == 1  # unverändert
    assert not (root / "versions" / ".tmp-v2").exists()


def test_sets_installer_skips_older(tmp_path, monkeypatch):
    """Version ≤ aktuell → skipped, kein Überschreiben."""
    import urllib.request

    zdata = _make_set_zip(version=1)

    class FakeResp:
        def read(self): return zdata
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=300: FakeResp())

    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    (v1 / "audio").mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    (v1 / "audio" / "akzent_001.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(json.dumps({"version": 1, "rows": []}))

    svc = BenchmarkService(root)
    res = svc.install_set_from_release(
        url="https://example.com/set.zip",
        expected_sha=hashlib.sha256(zdata).hexdigest(),
    )
    assert res["skipped"] and res["reason"] == "bereits installiert"
    assert svc.latest_manifest()["version"] == 1


def test_sets_installer_rejects_traversal(tmp_path, monkeypatch):
    """Zip mit Pfad-Traversal (../../etc/passwd) → abgelehnt, nichts geändert."""
    import urllib.request

    zdata = _make_set_zip(version=2, evil=True)

    class FakeResp:
        def read(self): return zdata
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=300: FakeResp())

    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    (v1 / "audio").mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    (v1 / "audio" / "akzent_001.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(json.dumps({"version": 1, "rows": []}))

    svc = BenchmarkService(root)
    with pytest.raises(RuntimeError, match="unerlaubter Zip-Eintrag"):
        svc.install_set_from_release(
            url="https://example.com/set.zip",
            expected_sha=hashlib.sha256(zdata).hexdigest(),
        )
    assert svc.latest_manifest()["version"] == 1
    assert not (root / "versions" / ".tmp-v2").exists()
    # nichts außerhalb entpackt
    assert not (tmp_path / "etc").exists()


# ── Benchmark-Set-Discovery (Change 076, git-basiert) ────────────────────


def _make_git_repo(tmp_path, versions=(1, 2), foreign_tag=True) -> Path:
    """Legt ein lokales Git-Repo mit benchmark-set-v<N>.zip + .sha256 an.

    Jede Version bekommt einen Tag benchmark-set-v<N>. Ein Fremd-Tag
    (foreign_tag) testet das Filtern. Rückgabe: Repo-Pfad (git_url).
    """
    import subprocess

    repo = tmp_path / "sets-repo"
    repo.mkdir()
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True, text=True,
                       env={**dict(__import__("os").environ),
                            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for v in versions:
        zdata = _make_set_zip(version=v, n_samples=1)
        sha = hashlib.sha256(zdata).hexdigest()
        (repo / f"benchmark-set-v{v}.zip").write_bytes(zdata)
        (repo / f"benchmark-set-v{v}.zip.sha256").write_text(
            f"{sha}  benchmark-set-v{v}.zip\n")
        git("add", "-A")
        git("commit", "-q", "-m", f"set v{v}")
        git("tag", f"benchmark-set-v{v}")
    if foreign_tag:
        (repo / "README.md").write_text("fremd")
        git("add", "-A")
        git("commit", "-q", "-m", "readme")
        git("tag", "other-release")
    return repo


def _install_root(tmp_path) -> Path:
    root = tmp_path / "benchmark_data"
    v1 = root / "versions" / "v1"
    (v1 / "audio").mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False))
    (v1 / "audio" / "akzent_001.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(json.dumps({"version": 1, "rows": []}))
    return root


def test_discover_sets_parses_tags(tmp_path):
    """Discovery via git ls-remote: parst Tags, filtert fremde, absteigend."""
    repo = _make_git_repo(tmp_path)
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    sets = svc.discover_sets(str(repo))
    assert [s["version"] for s in sets] == [2, 1]  # absteigend
    assert sets[0]["tag"] == "benchmark-set-v2"
    assert "other-release" not in [s["tag"] for s in sets]


def test_discover_sets_cached(tmp_path, monkeypatch):
    """Cache: zweiter Aufruf innerhalb 300 s → kein zweiter ls-remote."""
    repo = _make_git_repo(tmp_path)
    calls = []
    orig = BenchmarkService._run_git

    def counting_git(args, timeout):
        if args[0] == "ls-remote":
            calls.append(1)
        return orig(args, timeout)

    monkeypatch.setattr(BenchmarkService, "_run_git", staticmethod(counting_git))
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    svc.discover_sets(str(repo))
    svc.discover_sets(str(repo))
    assert len(calls) == 1  # Cache-Treffer


def test_install_via_git_uses_sha_file(tmp_path):
    """git-Install: clone des Tags, SHA aus .sha256-Datei, aktiviert v2."""
    repo = _make_git_repo(tmp_path, versions=(1, 2))
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    res = svc.install_set_from_release(git_url=str(repo))
    assert res["ok"] and not res["skipped"]
    assert res["installed_version"] == 2
    assert res["sha256"] == hashlib.sha256(
        _make_set_zip(version=2, n_samples=1)).hexdigest()
    assert svc.latest_manifest()["version"] == 2


def test_install_git_version_choice(tmp_path):
    """version-Arg wählt genau diese Version (v1 trotz vorhandenem v2)."""
    repo = _make_git_repo(tmp_path, versions=(1, 2))
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    # Version 1 ist ≤ aktuell (1) → skip, aber korrekt aufgelöst (nicht v2)
    res = svc.install_set_from_release(git_url=str(repo), version=1)
    assert res["skipped"] and res["reason"] == "bereits installiert"


def test_git_error_sets_last_error(tmp_path, monkeypatch):
    """git-Fehler (Repo existiert nicht) → RuntimeError, Status crasht nicht."""
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    with pytest.raises(RuntimeError, match="git ls-remote"):
        svc.discover_sets(str(tmp_path / "gibtsnicht"))
    from app.config import settings

    monkeypatch.setattr(settings, "BENCHMARK_SET_GIT_URL", str(tmp_path / "gibtsnicht"))
    monkeypatch.setattr(settings, "BENCHMARK_SET_URL", "")
    st = svc.set_status()
    assert st["available"] == []
    assert "Discovery fehlgeschlagen" in (st["last_error"] or "")


def test_git_missing_binary(tmp_path, monkeypatch):
    """git nicht installiert → klare RuntimeError-Meldung."""
    svc = BenchmarkService(_install_root(tmp_path))
    svc._set_discovery_cache.clear()
    monkeypatch.setattr(BenchmarkService, "GIT_BIN", "/nonexistent/git")
    with pytest.raises(RuntimeError, match="git ist nicht installiert"):
        svc.discover_sets("https://example.invalid/x.git")


def test_parse_sha_asset_formats():
    """sha256sum-Format und nackter Hash werden beide erkannt."""
    from app.benchmark_service import BenchmarkService

    sha = "ab" * 32
    assert BenchmarkService._parse_sha_asset(f"{sha}  benchmark-set-v2.zip".encode()) == sha
    assert BenchmarkService._parse_sha_asset(sha.encode()) == sha
    with pytest.raises(RuntimeError, match="keinen SHA256-Hash"):
        BenchmarkService._parse_sha_asset(b"kein hash hier")
