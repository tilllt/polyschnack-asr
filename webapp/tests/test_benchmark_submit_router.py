"""Tests für Benchmark-Selbstbedienung (Change 030):
GET /api/benchmark/package[/sha256] + POST /api/benchmark/submit."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="benchmark_submit_test_")
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("BENCHMARK_API_KEYS", "test-key-123")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.config import settings  # noqa: E402

MANIFEST = {
    "version": 1,
    "created_at": "2026-08-19T12:00:00Z",
    "created_by": "admin",
    "supersedes": None,
    "categories": [{"id": "clean", "name": "Clean", "kanal": "clean", "inhalt": "allgemein"}],
    "axes": {"kanal": {"beschreibung": "x", "kategorien": {"clean": {"name": "Clean"}}},
             "inhalt": {"beschreibung": "y", "kategorien": {"allgemein": {"name": "Allgemein"}}}},
    "samples": [
        {"id": "clean_001", "category": "clean", "kanal": "clean", "inhalt": "allgemein",
         "source_path": "common_voice_de_1.mp3", "text": "Guten Morgen.",
         "accent": "", "age": "", "held_out": False, "status": "active"},
        {"id": "clean_002", "category": "clean", "kanal": "clean", "inhalt": "allgemein",
         "source_path": "common_voice_de_2.mp3", "text": "Der Zug fährt ab.",
         "accent": "", "age": "", "held_out": False, "status": "active"},
        {"id": "clean_003", "category": "clean", "kanal": "clean", "inhalt": "allgemein",
         "source_path": "common_voice_de_3.mp3", "text": "Die Sonne scheint.",
         "accent": "", "age": "", "held_out": False, "status": "active"},
    ],
}


def _miniwav() -> bytes:
    import struct
    n = 400
    data = b"\x00\x00" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


def _make_v31_fixture(tmp_path: Path) -> Path:
    """Mini-V3.1-ZIP (Change 065): testset.json + audio/, wie Release v4.

    Gibt den ZIP-Pfad zurück; Settings (URL als file:// + SHA256) setzt die
    client-Fixture per monkeypatch — kein Netz nötig.
    """
    import zipfile

    root = tmp_path / "v31fix"
    audio = root / "audio"
    audio.mkdir(parents=True)
    testset = {
        "version": 4,
        "split": "public",
        "sample_rate": 16000,
        "split_seed": 42,
        "public_ratio": 0.6,
        "samples": [
            {"id": "clean_001", "kind": "de_synth", "variant": "lead2",
             "split": "public", "source": "piper-tts",
             "gt": [{"start": 2.0, "end": 2.4}]},
            {"id": "clean_002", "kind": "de_synth", "variant": "trail2",
             "split": "public", "source": "piper-tts",
             "gt": [{"start": 0.0, "end": 2.4}]},
            {"id": "clean_003", "kind": "de_synth", "variant": "both2",
             "split": "public", "source": "piper-tts",
             "gt": [{"start": 2.0, "end": 4.4}]},
        ],
    }
    (root / "testset.json").write_text(json.dumps(testset, ensure_ascii=False))
    for sid in ("clean_001", "clean_002", "clean_003"):
        (audio / f"{sid}.wav").write_bytes(_miniwav())
    zip_path = tmp_path / "vad-benchmark-v3.1-public.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(root / "testset.json", "testset.json")
        for sid in ("clean_001", "clean_002", "clean_003"):
            z.write(audio / f"{sid}.wav", f"audio/{sid}.wav")
    return zip_path


def package_hash(root: Path) -> str:
    """Deterministischer Paket-Hash (REQ-WEB-040): sha256(manifest) + je Audio-Datei."""
    vdir = root / "versions" / "v1"
    parts = [hashlib.sha256((vdir / "manifest.json").read_bytes()).digest()]
    for wav in sorted((vdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
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
    for sid in ("clean_001", "clean_002", "clean_003"):
        (audio / f"{sid}.wav").write_bytes(_miniwav())
    (root / "results").mkdir()
    (root / "results" / "latest.json").write_text(
        json.dumps({"version": 1, "rows": [{"backend": "ps-pk-onnx", "wer": 0.05}]})
    )
    (root / "pricing.json").write_text(json.dumps({"rows": []}))
    # Change 065: VAD-Paket kommt aus der V3.1-ZIP-Fixture (file://, kein Netz)
    v31 = _make_v31_fixture(tmp_path)
    monkeypatch.setattr(settings, "VAD_PACKAGE_URL", v31.as_uri())
    monkeypatch.setattr(settings, "VAD_PACKAGE_SHA256",
                        hashlib.sha256(v31.read_bytes()).hexdigest())
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "benchmark.db")
    monkeypatch.setattr(settings, "BENCHMARK_DATA_DIR", root)
    monkeypatch.setattr(settings, "BENCHMARK_API_KEYS", _TEST_KEY)
    with TestClient(app) as c:
        yield c


# ── GET /api/benchmark/package ────────────────────────────────────────────


def test_package_returns_tarball_with_sha_header(client):
    r = client.get("/api/benchmark/package", headers=_auth_headers())
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/gzip")
    sha_hdr = r.headers.get("x-benchmark-sha256", "")
    assert sha_hdr == "v1:" + package_hash(Path(settings.BENCHMARK_DATA_DIR))
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = sorted(tar.getnames())
    assert "manifest.json" in names
    assert all(f"audio/{sid}.wav" in names for sid in ("clean_001", "clean_002", "clean_003"))


def test_package_deterministic(client):
    a = client.get("/api/benchmark/package", headers=_auth_headers()).content
    b = client.get("/api/benchmark/package", headers=_auth_headers()).content
    assert a == b  # Byte-identisch (sortiert, mtime=0)


def test_package_sha256_endpoint(client):
    r = client.get("/api/benchmark/package/sha256", headers=_auth_headers())
    assert r.status_code == 200
    d = r.json()
    assert d["version"] == 1
    assert d["sha256"] == package_hash(Path(settings.BENCHMARK_DATA_DIR))
    # Konsistenz mit dem Tarball-Header
    hdr = client.get("/api/benchmark/package", headers=_auth_headers()).headers["x-benchmark-sha256"]
    assert hdr == f"v1:{d['sha256']}"


def test_package_404_without_data(tmp_path, monkeypatch):
    from app import db as db_module
    from sqlmodel import SQLModel, create_engine
    eng = create_engine(f"sqlite:///{tmp_path / 'b.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    root = tmp_path / "empty_benchmark"
    root.mkdir()
    monkeypatch.setattr(settings, "BENCHMARK_DATA_DIR", root)
    monkeypatch.setattr(settings, "BENCHMARK_API_KEYS", _TEST_KEY)
    with TestClient(app) as c:
        assert c.get("/api/benchmark/package", headers=_auth_headers()).status_code == 404
        assert c.get("/api/benchmark/package/sha256", headers=_auth_headers()).status_code == 404


# ── POST /api/benchmark/submit ────────────────────────────────────────────


def _submit_body(backend: str = "crispr-ark", sha: str | None = None,
                 version: int = 1, run_id: str = "test-run") -> dict:
    root = Path(settings.BENCHMARK_DATA_DIR)
    return {
        "backend": backend,
        "settings": "auto",
        "manifest_version": version,
        "manifest_sha256": sha or package_hash(root),
        "run_id": run_id,
        "generated_at": "2026-08-19T13:00:00Z",
        "rows": [
            {"sample_id": "clean_001", "hyp": "Guten Morgen.", "wer": 0.0, "cer": 0.0,
             "coverage_pct": 100.0, "rtf": 0.10},
            {"sample_id": "clean_002", "hyp": "Der Zug fährt ab.", "wer": 0.0, "cer": 0.0,
             "coverage_pct": 100.0, "rtf": 0.12},
            {"sample_id": "clean_003", "hyp": "", "wer": 1.0, "cer": 1.0,
             "coverage_pct": 0.0, "rtf": 0.09},
        ],
        "meta": {"n_audio_s": 0.075, "backend_version": "v0.8.29"},
    }


_TEST_KEY = "test-key-123"


def _auth_headers(body: dict | None = None, raw: bytes | None = None) -> dict:
    """Shared-Key-Header (Change 031): Bearer + optionale Body-Signatur.

    raw: exakt die Bytes, die gesendet werden (content=raw, wie der Runner).
    """
    h = {"Authorization": f"Bearer {_TEST_KEY}"}
    if body is not None:
        raw = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["X-Benchmark-Signature"] = hmac.new(
            _TEST_KEY.encode(), raw, hashlib.sha256).hexdigest()
    return h


def _post_submit(client, body: dict):
    """POST /submit mit content=raw + Signatur (identisch zum vast.ai-Runner)."""
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = _auth_headers(body, raw=raw)
    headers["Content-Type"] = "application/json"
    return client.post("/api/benchmark/submit", content=raw, headers=headers)


def test_submit_ok_updates_results(client):
    r = _post_submit(client, _submit_body())
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["backend"] == "crispr-ark"

    # latest.json neu gepoolt: nur Backends mit Run auf aktuellem Hash
    latest = json.loads((Path(settings.BENCHMARK_DATA_DIR) / "results" / "latest.json").read_text())
    assert [x["backend"] for x in latest["rows"]] == ["crispr-ark"]
    row = latest["rows"][0]
    assert row["n_samples"] == 3
    assert row["wer"] == pytest.approx(1.0 / 3.0)

    # runs/-Datei persistiert
    runs = list((Path(settings.BENCHMARK_DATA_DIR) / "results" / "runs").glob("crispr-ark_*.json"))
    assert len(runs) == 1
    run = json.loads(runs[0].read_text())
    assert run["manifest_sha256"] == d["sha256"]
    assert len(run["rows"]) == 3

    # pricing.json aktualisiert (RTF-basiert)
    pricing = json.loads((Path(settings.BENCHMARK_DATA_DIR) / "pricing.json").read_text())
    assert [x["backend"] for x in pricing["rows"]] == ["crispr-ark"]


def test_submit_hash_mismatch_409(client):
    r = _post_submit(client, _submit_body(sha="f" * 64))
    assert r.status_code == 409
    d = r.json()
    assert d["ok"] is False
    assert "current" in d
    # latest.json unverändert
    latest = json.loads((Path(settings.BENCHMARK_DATA_DIR) / "results" / "latest.json").read_text())
    assert [x["backend"] for x in latest["rows"]] == ["ps-pk-onnx"]


def test_submit_version_mismatch_409(client):
    r = _post_submit(client, _submit_body(version=99))
    assert r.status_code == 409


def test_submit_unknown_backend_422(client):
    r = _post_submit(client, _submit_body(backend="no-such-backend"))
    assert r.status_code == 422
    assert r.json()["ok"] is False


def test_submit_without_data_404(tmp_path, monkeypatch):
    from app import db as db_module
    from sqlmodel import SQLModel, create_engine
    eng = create_engine(f"sqlite:///{tmp_path / 'b.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    root = tmp_path / "empty2"
    root.mkdir()
    monkeypatch.setattr(settings, "BENCHMARK_DATA_DIR", root)
    monkeypatch.setattr(settings, "BENCHMARK_API_KEYS", _TEST_KEY)
    with TestClient(app) as c:
        # sha explizit setzen — der Default würde package_hash auf das leere
        # Verzeichnis anwenden und im Test (nicht im Server) fehlschlagen.
        r = _post_submit(c, _submit_body(sha="0" * 64))
        assert r.status_code == 404


def test_submit_twice_updates_pool(client):
    """Zwei Submits desselben Backends: Pooling über beide Runs (Mittelwert)."""
    _post_submit(client, _submit_body(run_id="run-a"))
    body = _submit_body(run_id="run-b")
    body["rows"][2]["wer"] = 0.0  # zweiter Lauf besser
    body["rows"][2]["cer"] = 0.0
    r = _post_submit(client, body)
    assert r.status_code == 200
    latest = json.loads((Path(settings.BENCHMARK_DATA_DIR) / "results" / "latest.json").read_text())
    row = latest["rows"][0]
    assert row["n_samples"] == 6  # beide Runs gepoolt
    # Run A: WER (0+0+1)/3 · Run B: (0+0+0)/3 → Summe 1.0 über 6 Samples
    assert row["wer"] == pytest.approx(1.0 / 6)


# ── Shared-Key-Auth (Change 031) ─────────────────────────────────────────


def test_package_requires_key_401(client):
    assert client.get("/api/benchmark/package").status_code == 401
    assert client.get("/api/benchmark/package/sha256").status_code == 401


def test_package_wrong_key_401(client):
    h = {"Authorization": "Bearer falscher-key"}
    assert client.get("/api/benchmark/package", headers=h).status_code == 401
    assert client.get("/api/benchmark/package/sha256", headers=h).status_code == 401


def test_package_not_configured_503(client, monkeypatch):
    monkeypatch.setattr(settings, "BENCHMARK_API_KEYS", "")
    r = client.get("/api/benchmark/package", headers=_auth_headers())
    assert r.status_code == 503


def test_submit_without_key_401(client):
    body = _submit_body()
    r = client.post("/api/benchmark/submit", json=body)
    assert r.status_code == 401


def test_submit_missing_signature_401(client):
    body = _submit_body()
    r = client.post("/api/benchmark/submit", json=body,
                    headers={"Authorization": f"Bearer {_TEST_KEY}"})
    assert r.status_code == 401


def test_submit_bad_signature_401(client):
    body = _submit_body()
    h = _auth_headers(body)
    h["X-Benchmark-Signature"] = "0" * 64
    r = client.post("/api/benchmark/submit", json=body, headers=h)
    assert r.status_code == 401


def test_submit_signature_binds_to_key(client):
    """Signatur muss mit dem Key im Bearer-Header passen (nicht keys[0])."""
    body = _submit_body()
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    sig_other = hmac.new(b"anderer-key", raw, hashlib.sha256).hexdigest()
    h = {"Authorization": f"Bearer {_TEST_KEY}", "X-Benchmark-Signature": sig_other}
    r = client.post("/api/benchmark/submit", json=body, headers=h)
    assert r.status_code == 401


# ── Change 062: VAD-Submit (kind="vad") ───────────────────────────────────

def _vad_submit_body(backend: str = "silero-onnx", sha: str | None = None,
                     version: int = 1) -> dict:
    from app.benchmark_service import BenchmarkService

    root = Path(settings.BENCHMARK_DATA_DIR)
    svc = BenchmarkService(root)
    vad_sha = sha or svc.vad_package_sha256(version)
    return {
        "backend": backend,
        "kind": "vad",
        "settings": "auto",
        "manifest_version": version,
        "manifest_sha256": vad_sha,
        "run_id": "vad-run-1",
        "generated_at": "2026-08-21T09:00:00Z",
        "rows": [
            {"sample_id": "clean_001", "vad_f1": 0.96, "boundary_start_ms": 16.0,
             "boundary_end_ms": 72.0, "fp_time_s": 0.0, "rtf": 0.02},
            {"sample_id": "clean_002", "vad_f1": 0.94, "boundary_start_ms": 20.0,
             "boundary_end_ms": 60.0, "fp_time_s": 0.0, "rtf": 0.02},
            {"sample_id": "clean_003", "vad_f1": 0.92, "boundary_start_ms": 12.0,
             "boundary_end_ms": 80.0, "fp_time_s": 0.5, "rtf": 0.03},
        ],
        "meta": {"engine": "silero_onnx"},
    }


def test_vad_submit_ok_pools_separately(client):
    r = _post_submit(client, _vad_submit_body())
    assert r.status_code == 200
    assert r.json()["ok"] is True
    latest = json.loads((Path(settings.BENCHMARK_DATA_DIR) / "results" / "latest.json").read_text())
    # VAD-Run erscheint NICHT im ASR-Pool (kein wer) …
    assert latest["rows"] == []
    # … aber in der neuen vad-Sektion
    vad = latest["vad"]
    assert len(vad) == 1
    assert vad[0]["backend"] == "silero-onnx"
    assert vad[0]["n_samples"] == 3
    assert vad[0]["vad_f1_mean"] == pytest.approx(0.94, abs=0.001)
    assert vad[0]["boundary_start_ms_median"] == pytest.approx(16.0)
    assert vad[0]["boundary_end_ms_median"] == pytest.approx(72.0)
    assert vad[0]["fp_time_s"] == pytest.approx(0.5)
    # Change 065: testset_version + Release-URL aus dem V3.1-Paket
    assert vad[0]["testset_version"] == "v4-public"
    assert "vad-benchmark-v3.1-public.zip" in vad[0]["testset_release_url"]
    # Run-Datei trägt kind="vad"
    runs = list((Path(settings.BENCHMARK_DATA_DIR) / "results" / "runs").glob("silero-onnx_*.json"))
    assert len(runs) == 1
    assert json.loads(runs[0].read_text())["kind"] == "vad"


def test_vadpackage_sha256_reports_testset_version(client):
    """Change 065: /vadpackage/sha256 verrät Testset-Version + Release-URL."""
    r = client.get("/api/benchmark/vadpackage/sha256", headers=_auth_headers())
    assert r.status_code == 200
    d = r.json()
    assert d["testset_version"] == "v4-public"
    assert "vad-benchmark-v3.1-public.zip" in d["testset_release_url"]
    assert len(d["sha256"]) == 64


def test_vad_submit_unknown_model_rejected(client):
    r = _post_submit(client, _vad_submit_body(backend="does-not-exist-vad"))
    assert r.status_code == 422
    assert r.json()["reason"] == "unknown backend"


def test_vad_submit_reference_model_allowed(client):
    """Lizenz-inkompatible Referenz-Modelle (ten-vad) sind benchmarkbar."""
    r = _post_submit(client, _vad_submit_body(backend="ten-vad"))
    assert r.status_code == 200
    assert r.json()["ok"] is True
