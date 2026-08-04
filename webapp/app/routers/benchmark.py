"""Benchmark-API (Task D) — öffentliche Read-Routen + Admin-POST.

Öffentlich (kein Login):
    GET /api/benchmark/meta            — Methodik, Kategorien, Version, Stand
    GET /api/benchmark/samples         — aktive, nicht-held-out Samples
    GET /api/benchmark/audio/{id}      — finale WAV (unkomprimiert, Range)
    GET /api/benchmark/preview/{id}    — Preview-MP3 (128k, on-demand)
    GET /api/benchmark/results         — gepoolte Ergebnisse (latest.json)
    GET /api/benchmark/pricing         — Preisvergleich (WER/€)
    GET /api/benchmark/versions        — Versions-History

Admin (require_admin):
    POST /api/benchmark/samples/{id}/reject  — Ablehnen → Auto-Ersatz + vN+1
    POST /api/benchmark/samples/{id}/edit    — Metadaten editieren
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..benchmark_service import BenchmarkService
from ..config import settings
from ..deps import require_admin

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


def _service() -> BenchmarkService:
    return BenchmarkService(settings.BENCHMARK_DATA_DIR)


def _require_data() -> BenchmarkService:
    """404 statt Crash, wenn noch keine Benchmark-Daten existieren."""
    svc = _service()
    try:
        svc.latest_manifest()
    except FileNotFoundError:
        raise HTTPException(404, "no benchmark data available")
    return svc


# ── Öffentliche GET-Routen ────────────────────────────────────────────────


@router.get("/meta")
def meta() -> Dict[str, Any]:
    svc = _require_data()
    m = svc.latest_manifest()
    public = svc.public_samples()
    return {
        "version": m["version"],
        "created_at": m.get("created_at"),
        "supersedes": m.get("supersedes"),
        "categories": m.get("categories", []),
        "sample_count": len(public),
        "per_category": _count_by_category(public),
        "methodology": m.get("methodology", "WER/CER/RTF auf CommonVoice-de + TTS"),
        "disclaimer": m.get(
            "disclaimer",
            "Held-out-Samples und Referenztexte sind nicht öffentlich "
            "(Anti-Gaming). Ergebnisse sind Momentaufnahmen.",
        ),
    }


@router.get("/samples")
def samples() -> Dict[str, Any]:
    svc = _require_data()
    m = svc.latest_manifest()
    public = svc.public_samples()
    return {
        "version": m["version"],
        "samples": [
            {
                "id": s["id"],
                "category": s["category"],
                "text": s["text"],  # Referenztext: öffentlich sichtbar (nicht held-out)
                "accent": s.get("accent", ""),
                "age": s.get("age", ""),
                "preview_url": f"/api/benchmark/preview/{s['id']}",
                "audio_url": f"/api/benchmark/audio/{s['id']}",
            }
            for s in public
        ],
    }


@router.get("/audio/{sample_id}")
def audio(sample_id: str) -> FileResponse:
    svc = _require_data()
    try:
        path = svc.sample_audio_path(sample_id, kind="final")
    except KeyError:
        raise HTTPException(404, "sample not found")
    if not path.exists():
        raise HTTPException(404, "audio not available")
    return FileResponse(path, media_type="audio/wav", filename=f"{sample_id}.wav")


@router.get("/preview/{sample_id}")
def preview(sample_id: str) -> FileResponse:
    svc = _require_data()
    try:
        path = svc.ensure_preview(sample_id)
    except KeyError:
        raise HTTPException(404, "sample not found")
    except FileNotFoundError:
        raise HTTPException(404, "preview not available")
    return FileResponse(path, media_type="audio/mpeg", filename=f"{sample_id}.mp3")


@router.get("/results")
def results() -> Dict[str, Any]:
    """Gepoolte Benchmark-Ergebnisse (results/latest.json)."""
    svc = _service()
    p = svc.data_dir / "results" / "latest.json"
    if not p.exists():
        raise HTTPException(404, "no benchmark results yet")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/pricing")
def pricing() -> Dict[str, Any]:
    """Preisvergleich: Selbstkosten vs. SaaS vs. kommerziell (aus pricing.json + results)."""
    svc = _service()
    p = svc.data_dir / "pricing.json"
    if not p.exists():
        raise HTTPException(404, "no pricing data yet")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/versions")
def versions() -> Dict[str, Any]:
    svc = _service()
    nums = svc.version_numbers()
    out = []
    for n in nums:
        m = svc._load_manifest(n)
        out.append(
            {
                "version": n,
                "created_at": m.get("created_at"),
                "supersedes": m.get("supersedes"),
                "samples": len(m["samples"]),
                "active": sum(1 for s in m["samples"] if s["status"] == "active"),
                "rejected": sum(1 for s in m["samples"] if s["status"] == "rejected"),
            }
        )
    return {"versions": out}


# ── Admin-POST-Routen ─────────────────────────────────────────────────────


class SampleEdit(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    accent: Optional[str] = None
    age: Optional[str] = None
    held_out: Optional[bool] = None


@router.post("/samples/{sample_id}/reject", dependencies=[Depends(require_admin)])
def reject_sample(sample_id: str) -> Dict[str, Any]:
    """Lehnt ein Sample ab: Auto-Ersatz aus dem CV-Pool + neue Version vN+1."""
    svc = _require_data()
    m = svc.latest_manifest()
    sample = next((s for s in m["samples"] if s["id"] == sample_id), None)
    if sample is None:
        raise HTTPException(404, "sample not found")

    used_paths = {s["source_path"] for s in m["samples"]}
    used_ids = {s["id"] for s in m["samples"]}
    replacement = svc.replace_rejected_sample(
        category=sample["category"],
        exclude_ids=used_ids,
        used_paths=used_paths,
        seed=42,
    )
    if replacement is None:
        raise HTTPException(409, "kein Ersatz-Sample im CV-Pool verfügbar")

    new_manifest = svc.create_version_after_reject(sample_id, replacement)
    return {
        "ok": True,
        "old_version": m["version"],
        "new_version": new_manifest["version"],
        "rejected": sample_id,
        "replacement": replacement["id"],
        "replacement_source": replacement["source_path"],
    }


@router.post("/samples/{sample_id}/edit", dependencies=[Depends(require_admin)])
def edit_sample(sample_id: str, body: SampleEdit) -> Dict[str, Any]:
    """Editiert Metadaten der aktuellen Version in-place."""
    svc = _require_data()
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "keine Felder zum Editieren")
    try:
        s = svc.edit_sample(sample_id, **fields)
    except KeyError:
        raise HTTPException(404, "sample not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "sample": s}


# ── Helfer ────────────────────────────────────────────────────────────────


def _count_by_category(samples: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for s in samples:
        out[s["category"]] = out.get(s["category"], 0) + 1
    return out
