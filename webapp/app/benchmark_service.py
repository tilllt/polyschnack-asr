"""BenchmarkService — versionierte Benchmark-Manifeste + Sample-Verwaltung.

Datenlayout (benchmark_data/):
    versions/
        v1/
            manifest.json   # Samples, Kategorien, Version-Metadaten
            audio/          # finale WAV (unkomprimiert, Benchmark-Qualität)
            preview/        # MP3 128k (on-demand generiert, iOS-kompatibel)
        v2/ ...
    results/
        latest.json         # gepoolte Benchmark-Ergebnisse (WER/CER/RTF/€)

Reject-Regel: Manifeste sind immutable. Ein Reject erzeugt vN+1 (altes Sample
status=rejected, Ersatz aus CV-Pool eingefügt, supersedes=vN). Metadaten-Edits
mutieren die aktuelle Version in-place (updated_at).
"""
from __future__ import annotations

import copy
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

PREVIEW_BITRATE = "128k"


class BenchmarkService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    # ── Versionen / Manifeste ──────────────────────────────────────────────

    def _versions_dir(self) -> Path:
        return self.data_dir / "versions"

    def version_numbers(self) -> List[int]:
        return sorted(
            int(p.name[1:]) for p in self._versions_dir().glob("v*") if p.is_dir()
        )

    def latest_manifest(self) -> dict:
        nums = self.version_numbers()
        if not nums:
            raise FileNotFoundError("keine Benchmark-Version vorhanden")
        return self._load_manifest(nums[-1])

    def _load_manifest(self, version: int) -> dict:
        p = self._versions_dir() / f"v{version}" / "manifest.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _manifest_path(self, version: int) -> Path:
        return self._versions_dir() / f"v{version}" / "manifest.json"

    def _version_dir(self, version: int) -> Path:
        return self._versions_dir() / f"v{version}"

    # ── Öffentliche Sicht ──────────────────────────────────────────────────

    def public_samples(self) -> List[dict]:
        m = self.latest_manifest()
        return [
            s for s in m["samples"] if s["status"] == "active" and not s["held_out"]
        ]

    def categories(self) -> List[dict]:
        return self.latest_manifest().get("categories", [])

    def sample_audio_path(self, sample_id: str, kind: str = "final") -> Path:
        """Pfad zur Audio-Datei: final = WAV, preview = MP3 (on-demand)."""
        m = self.latest_manifest()
        version = m["version"]
        for s in m["samples"]:
            if s["id"] == sample_id:
                if kind == "final":
                    return self._version_dir(version) / "audio" / f"{sample_id}.wav"
                if kind == "preview":
                    return self._version_dir(version) / "preview" / f"{sample_id}.mp3"
                raise ValueError(f"unbekannter kind: {kind}")
        raise KeyError(sample_id)

    # ── Admin: Reject / Edit / Versionen ───────────────────────────────────

    def replace_rejected_sample(
        self,
        category: str,
        exclude_ids: set,
        pool: Optional[List[dict]] = None,
        seed: int = 42,
        used_paths: Optional[set] = None,
    ) -> Optional[dict]:
        """Wählt ein Ersatz-Sample aus dem CV-Pool (deterministisch).

        - ``pool``: injizierter Kandidaten-Pool (sonst cv_extract filter_cv_targets)
        - ``exclude_ids``: bereits verbrauchte Sample-IDs
        - ``used_paths``: bereits im Manifest verwendete source_paths (Pfad-Dedupe)
        - Neue ID: ``<category>_<nnn>`` (niedrigste freie Nummer ab 1)
        """
        used_paths = used_paths or set()
        if pool is None:
            # Default: CV-Metadaten (benchmark_data/cv/validated.tsv) via cv_extract
            pool = self._load_cv_pool(category)
        # Pfad-Dedupe: bereits verwendete Quellen ausschließen
        candidates = [e for e in pool if e["path"] not in used_paths]
        if not candidates:
            log.warning("kein Ersatz für Kategorie %s (Pool leer oder verbraucht)", category)
            return None
        import random
        rng = random.Random(seed)
        pick = rng.choice(candidates)
        used_ids = exclude_ids
        n = 1
        while f"{category}_{n:03d}" in used_ids:
            n += 1
        return {
            "id": f"{category}_{n:03d}",
            "category": category,
            "source_path": pick["path"],
            "text": pick["text"],
            "accent": pick.get("accent", ""),
            "age": pick.get("age", ""),
            "held_out": False,
            "status": "active",
        }

    def _load_cv_pool(self, category: str) -> List[dict]:
        """Liest den CV-Metadaten-Pool (validated.tsv) für Ersatz-Samples."""
        import sys
        from pathlib import Path as _P
        # cv_extract liegt im benchmark-Repo; fallback: gepoolte candidates.json
        candidates = self.data_dir / "cv" / "candidates.json"
        if candidates.exists():
            data = json.loads(candidates.read_text(encoding="utf-8"))
            return data.get(category, [])
        tsv = self.data_dir / "cv" / "validated.tsv"
        if not tsv.exists():
            return []
        sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
        from benchmark.cv_extract import filter_cv_targets  # type: ignore
        sel = filter_cv_targets(tsv, want={category: 50}, seed=7)
        return sel.get(category, [])

    def create_version_after_reject(self, sample_id: str, replacement: dict) -> dict:
        """Erzeugt vN+1: altes Sample → rejected, Ersatz eingefügt."""
        m = self.latest_manifest()
        new_version = m["version"] + 1
        new_manifest = copy.deepcopy(m)
        new_manifest["version"] = new_version
        new_manifest["supersedes"] = m["version"]
        new_manifest["created_at"] = _now_iso()
        found = False
        for s in new_manifest["samples"]:
            if s["id"] == sample_id:
                s["status"] = "rejected"
                found = True
                break
        if not found:
            raise KeyError(sample_id)
        new_manifest["samples"].append(replacement)

        vdir = self._version_dir(new_version)
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "audio").mkdir(exist_ok=True)
        (vdir / "preview").mkdir(exist_ok=True)
        tmp = self._manifest_path(new_version).with_suffix(".tmp")
        tmp.write_text(json.dumps(new_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._manifest_path(new_version))
        return new_manifest

    def edit_sample(self, sample_id: str, **fields: Any) -> dict:
        """Mutiert Metadaten der aktuellen Version in-place (nicht Status/ID)."""
        m = self.latest_manifest()
        version = m["version"]
        for s in m["samples"]:
            if s["id"] == sample_id:
                for k, v in fields.items():
                    if k in ("id", "status"):
                        raise ValueError(f"Feld {k} nicht editierbar")
                    s[k] = v
                m["updated_at"] = _now_iso()
                tmp = self._manifest_path(version).with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                tmp.replace(self._manifest_path(version))
                return s
        raise KeyError(sample_id)

    # ── Preview-Generierung ────────────────────────────────────────────────

    def ensure_preview(self, sample_id: str, src: Optional[Path] = None) -> Path:
        """Erzeugt Preview-MP3 (128k) aus der finalen WAV, gecacht."""
        dest = self.sample_audio_path(sample_id, kind="preview")
        if dest.exists():
            return dest
        if src is None:
            src = self.sample_audio_path(sample_id, kind="final")
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src),
                "-codec:a", "libmp3lame", "-b:a", PREVIEW_BITRATE, "-ac", "1",
                str(dest),
            ],
            check=True, timeout=300,
        )
        return dest


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
