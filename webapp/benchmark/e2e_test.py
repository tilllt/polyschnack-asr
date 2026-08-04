#!/usr/bin/env python3
"""End-to-End: Benchmark-API gegen ein Seeded benchmark_data-Verzeichnis."""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="e2e_bench_"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # webapp/

from pathlib import Path

from fastapi.testclient import TestClient

from app import db as db_module
from app.config import settings
from app.main import app
from sqlmodel import SQLModel, create_engine

SEED = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/seed_test")

settings.BENCHMARK_DATA_DIR = SEED
settings.OIDC_ENABLED = False
eng = create_engine(f"sqlite:///{SEED}/e2e.db", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(eng)
db_module.engine = eng

with TestClient(app) as c:
    meta = c.get("/api/benchmark/meta")
    mj = meta.json()
    print("meta:", meta.status_code, "| version:", mj["version"], "| samples:", mj["sample_count"])
    assert meta.status_code == 200 and mj["sample_count"] > 0

    samples = c.get("/api/benchmark/samples").json()
    print("samples:", len(samples["samples"]))
    assert len(samples["samples"]) == mj["sample_count"]

    first = samples["samples"][0]["id"]
    r = c.get(f"/api/benchmark/preview/{first}")
    print("preview:", r.status_code, r.headers.get("content-type"), len(r.content), "Bytes")
    assert r.status_code == 200 and r.headers.get("content-type", "").startswith("audio/mpeg")

    r2 = c.get(f"/api/benchmark/audio/{first}", headers={"Range": "bytes=0-99"})
    print("audio range:", r2.status_code, len(r2.content), "Bytes")
    assert r2.status_code == 206

    r3 = c.get("/api/benchmark/versions")
    print("versions:", r3.status_code, r3.json()["versions"][0]["active"], "aktiv")
    assert r3.status_code == 200

    r4 = c.post(f"/api/benchmark/samples/{first}/reject")
    print("reject (anon):", r4.status_code)
    assert r4.status_code in (401, 403)

print("E2E OK ✅")
