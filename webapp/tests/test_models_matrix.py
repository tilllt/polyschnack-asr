"""Feature-Matrix-Tests (Task 3) + FunASR-Rauswurf-Verifikation."""
from __future__ import annotations

import os
import re
from pathlib import Path

from app.routers.matrix import build_matrix


def test_matrix_contains_all_services():
    matrix = build_matrix()
    names = {m["name"] for m in matrix}
    assert {"ps-pk-onnx", "crispr-pk-cpp", "crispr-qwen3", "crispr-ark", "ps-voxtral"} <= names


def test_matrix_field_shapes():
    for m in build_matrix():
        for key in ("name", "backend", "model", "type", "status", "device",
                    "languages", "word_timestamps", "streaming", "async_jobs",
                    "noise_reduce", "vad", "diarization", "enhance", "requires"):
            assert key in m, f"missing {key} in {m['name']}"
        assert m["concurrency"] >= 1
        assert isinstance(m["device"], list) and m["device"]
        assert isinstance(m["languages"], list) and m["languages"]


def test_pk_python_capabilities():
    m = next(x for x in build_matrix() if x["name"] == "ps-pk-onnx")
    assert m["streaming"] is True
    assert m["word_timestamps"] is True
    assert m["type"] == "local"


def test_voxtral_local_and_timestamps_unverified():
    m = next(x for x in build_matrix() if x["name"] == "ps-voxtral")
    assert m["type"] == "local"
    assert m["word_timestamps"] == "verify"  # Mistral: not trained for timestamps
    assert m["streaming"] is True


def test_voxtral_profile_in_registry():
    from app.service_registry import get_service
    svc = get_service("ps-voxtral")
    assert svc is not None
    assert svc["compose_profile"] == "ps-voxtral"


def test_no_funasr_anywhere():
    """FunASR fliegt raus — kein Vorkommen in aktivem Code/Doku (nur zh/en, kein Deutsch).

    .hermes/plans/ ist ausgenommen: Plan-Dateien dokumentieren den Rauswurf selbst.
    """
    repo = Path(__file__).resolve().parent.parent.parent  # pk-asr/
    hits = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", "__pycache__", ".hermes")]
        for fn in files:
            if not fn.endswith((".py", ".md", ".yml", ".yaml", ".toml", ".ts", ".tsx", ".txt")):
                continue
            p = Path(root) / fn
            if p == Path(__file__).resolve():
                continue  # dieser Test selbst referenziert den Namen
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            if re.search(r"funasr", text, re.IGNORECASE):
                hits.append(str(p))
    assert hits == [], f"FunASR-Referenzen gefunden: {hits}"
