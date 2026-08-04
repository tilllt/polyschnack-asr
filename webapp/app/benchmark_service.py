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
