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
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .service_registry import get_service


def _median(vals: List[float]) -> float:
    """Median (numpy-frei, für _vad_summary)."""
    s = sorted(vals)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ── VAD-Paket-Helfer (Change 062) ─────────────────────────────────────────

def _wav_to_float16k(path: Path):
    """WAV → mono float32 [-1,1] @ 16 kHz (ffmpeg)."""
    import numpy as np

    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
        capture_output=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {out.stderr.decode(errors='ignore')[:120]}")
    return np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32767.0


def _write_wav16k(path: Path, wav) -> None:
    import io
    import wave

    import numpy as np

    s16 = (np.clip(wav, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(s16.tobytes())
    path.write_bytes(buf.getvalue())


def _vad_regions(probs, num_samples: int, window: int,
                 threshold: float, min_speech_ms: int = 250,
                 min_silence_ms: int = 400, speech_pad_ms: int = 120) -> List[tuple]:
    """Region-Logik (silero-Semantik, wie webapp/app/vad.py)."""
    min_speech = int(16000 * min_speech_ms / 1000)
    min_silence = int(16000 * min_silence_ms / 1000)
    pad = int(16000 * speech_pad_ms / 1000)
    regions: List[list] = []
    current = None
    silence = 0
    for i, p in enumerate(probs):
        start = i * window
        end = start + window
        if p >= threshold:
            silence = 0
            if current is None:
                current = [start, end]
            else:
                current[1] = end
        else:
            silence += window
            if current is not None and silence >= min_silence:
                if current[1] - current[0] > min_speech:
                    regions.append(current)
                current = None
    if current is not None and current[1] - current[0] > min_speech:
        regions.append(current)
    out = []
    for r in regions:
        s = max(0, r[0] - pad)
        e = min(num_samples, r[1] + pad)
        if e > s:
            out.append((s / 16000, e / 16000))
    return out


def _energy_gt(wav, window: int = 512, thresh_db: float = -40.0) -> List[tuple]:
    """Energie-Regionen (VAD-freie GT-Basis)."""
    import numpy as np

    probs = np.array([
        1.0 if np.sqrt((wav[i * window:(i + 1) * window] ** 2).mean()) > 10 ** (thresh_db / 20)
        else 0.0
        for i in range((wav.size - window) // window + 1)
    ], dtype=np.float32)
    return _vad_regions(probs, wav.size, window=window, threshold=0.5)


def _shift_mid(seg, mid_at: float, mid_len: float) -> List[tuple]:
    s, e = seg
    if e <= mid_at:
        return [(s, e)]
    if s >= mid_at:
        return [(s + mid_len, e + mid_len)]
    return [(s, mid_at), (mid_at + mid_len, e + mid_len)]

log = logging.getLogger(__name__)

PREVIEW_BITRATE = "128k"

# Selbstkosten-Annahme €/min je Backend (identisch zu run_container.py —
# dient als Basis fürs RTF-basierte Pricing nach Submits).
BACKEND_COST_ASSUMPTION = {
    "ps-pk-onnx": 0.0002, "crispr-pk-cpp": 0.0002, "crispr-qwen3": 0.0004,
    "crispr-ark": 0.0006, "crispr-moonshine-de": 0.0001, "crispr-canary": 0.0003,
    "crispr-voxtral": 0.0004, "crispr-whisper": 0.0002,
}


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

    def _vad_summary(self, runs_dir: Path) -> List[dict]:
        """VAD-Ergebnis-Zusammenfassung (Change 062/065): je Backend F1/Boundaries/FP/RTF.

        Sammelt Runs mit kind=="vad" + aktuellem VAD-Paket-Hash; ASR-Runs
        (ohne vad_f1) werden ignoriert — der ASR-Pool bleibt unberührt.
        Change 065: Hash = vad_package_sha256 (vorher fälschlich der ASR-Hash
        → VAD-Sektion blieb leer); testset_version/release_url aus dem
        Paket-Manifest.
        """
        from app.config import settings

        m = self.latest_manifest()
        vad_sha = self.vad_package_sha256(m["version"])
        try:
            pkg_manifest = json.loads(
                (self.data_dir / "versions" / f"v{m['version']}" / "vad" /
                 "vad-manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pkg_manifest = {}
        testset_version = pkg_manifest.get("testset_version", "")
        release_url = pkg_manifest.get(
            "testset_release_url", settings.VAD_PACKAGE_URL.strip()
            or self.V31_RELEASE_URL)
        by_backend: Dict[str, List[dict]] = {}
        for rf in runs_dir.glob("*.json"):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("kind") != "vad" or data.get("manifest_sha256") != vad_sha:
                continue
            rows = [r for r in data.get("rows", []) if r.get("vad_f1") is not None]
            by_backend.setdefault(data["backend"], []).extend(rows)
        out: List[dict] = []
        for bname, rows in by_backend.items():
            n = len(rows)
            if not n:
                continue
            bs = sorted(r.get("boundary_start_ms") or 0 for r in rows)
            be = sorted(r.get("boundary_end_ms") or 0 for r in rows)
            out.append({
                "backend": bname,
                "kind": "vad",
                "testset_version": testset_version,
                "testset_release_url": release_url,
                "n_samples": n,
                "vad_f1_mean": round(sum(r["vad_f1"] for r in rows) / n, 4),
                "boundary_start_ms_median": _median(bs),
                "boundary_end_ms_median": _median(be),
                "fp_time_s": round(sum(r.get("fp_time_s") or 0 for r in rows), 2),
                "rtf_mean": round(sum(r.get("rtf") or 0 for r in rows) / n, 4),
            })
        out.sort(key=lambda r: r["backend"])
        return out

    # ── Aligner-Benchmark (Change 132) ─────────────────────────────────────

    def _aligner_summary(self, runs_dir: Path) -> List[dict]:
        """Aligner-Ergebnis-Zusammenfassung (Change 132): je Aligner
        Wortabdeckung/0-Dauer/Audio-Abdeckung/RTF + Kreuz-Δ.

        Sammelt Runs mit kind=="aligner" (je Aligner) + kind=="aligner_cross"
        (paarweises |Δ start|-Median) — nur Runs zum aktiven Manifest-Hash.
        ASR-/VAD-Runs werden ignoriert.
        """
        m = self.latest_manifest()
        sha = self.package_sha256(m["version"])
        by_backend: Dict[str, List[dict]] = {}
        cross_rows: List[dict] = []
        for rf in runs_dir.glob("*.json"):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("manifest_sha256") != sha:
                continue
            kind = data.get("kind")
            if kind == "aligner":
                rows = [r for r in data.get("rows", [])
                        if r.get("word_coverage_pct") is not None]
                by_backend.setdefault(data["backend"], []).extend(rows)
            elif kind == "aligner_cross":
                cross_rows.extend(data.get("rows", []))

        out: List[dict] = []
        for bname, rows in by_backend.items():
            n = len(rows)
            if not n:
                continue
            out.append({
                "backend": bname,
                "kind": "aligner",
                "n_samples": n,
                "word_coverage_mean": round(
                    sum(r.get("word_coverage_pct") or 0 for r in rows) / n, 1),
                "zero_duration_total": sum(r.get("n_zero") or 0 for r in rows),
                "audio_coverage_mean": round(
                    sum(r.get("audio_coverage_pct") or 0 for r in rows) / n, 1),
                "rtf_mean": round(
                    sum(r.get("rtf") or 0 for r in rows) / n, 4),
            })
        out.sort(key=lambda r: r["backend"])

        cross = sorted(cross_rows, key=lambda r: r.get("pair", ""))
        if cross:
            out.append({
                "backend": "kreuz-Δ",
                "kind": "aligner_cross",
                "n_samples": 0,
                "pairs": cross,
            })
        return out

    # ── VAD-Benchmark-Paket (Change 062/065) ────────────────────────────────

    V31_RELEASE_URL = ("https://github.com/tilllt/vad-benchmark-data/releases/"
                       "download/v4/vad-benchmark-v3.1-public.zip")

    def _fetch_v31_zip(self, version: int) -> Path:
        """V3.1-public-ZIP herunterladen (SHA256-verifiziert), gecacht.

        Change 065: Das VAD-Paket wird aus dem offiziellen Testset-Artefakt
        (GitHub-Release v4) importiert statt aus dem ASR-Manifest generiert.
        SHA256-Mismatch → RuntimeError (kein stiller Fallback auf das alte
        Set — das wäre ein still falsches Paket).
        """
        import urllib.request
        import zipfile

        from app.config import settings

        pkg = self.data_dir / "versions" / f"v{version}" / "vad"
        pkg.mkdir(parents=True, exist_ok=True)
        cache = pkg / "v3.1-public.zip"
        expected = settings.VAD_PACKAGE_SHA256.strip().lower()
        url = settings.VAD_PACKAGE_URL.strip() or self.V31_RELEASE_URL

        def _verify(path: Path) -> bool:
            if not path.exists():
                return False
            return hashlib.sha256(path.read_bytes()).hexdigest() == expected

        if not _verify(cache):
            print(f"[benchmark] Lade V3.1-public-Paket von {url} …")
            with urllib.request.urlopen(url, timeout=300) as r:
                raw = r.read()
            got = hashlib.sha256(raw).hexdigest()
            if got != expected:
                raise RuntimeError(
                    f"V3.1-Paket-SHA256-Mismatch: erwartet {expected}, "
                    f"erhalten {got} — Abbruch (kein Fallback auf altes Set)")
            cache.write_bytes(raw)
            print(f"[benchmark] V3.1-Paket gecacht ({len(raw) / 1e6:.1f} MB)")
        with zipfile.ZipFile(cache) as z:
            z.extractall(pkg / "import", members=[m for m in z.namelist() if not m.startswith("__")])
        return pkg / "import" / "testset.json"

    def build_vad_package(self, version: int) -> Path:
        """VAD-Paket (Change 065): importiert das V3.1-public-Testset.

        Statt Stille-Insertions-Varianten aus dem ASR-Manifest zu generieren
        (V2-Methodik) wird das offizielle V3.1-Artefakt verwendet (235 public
        Samples: Piper-TTS + Common-Voice, DEMAND-SNR, Noise/Musik-FP, exakte
        GT). Gecacht unter versions/v{version}/vad/.
        """
        from app.config import settings

        pkg = self.data_dir / "versions" / f"v{version}" / "vad"
        if (pkg / "vad-manifest.json").exists():
            return pkg
        pkg.mkdir(parents=True, exist_ok=True)
        out_audio = pkg / "audio"
        out_audio.mkdir(exist_ok=True)

        ts_path = self._fetch_v31_zip(version)
        ts = json.loads(ts_path.read_text(encoding="utf-8"))
        import_dir = ts_path.parent
        samples_out: List[dict] = []
        for s in ts.get("samples", []):
            sid = s["id"]
            src = import_dir / "audio" / f"{sid}.wav"
            if not src.exists():
                continue
            shutil.copyfile(src, out_audio / f"{sid}.wav")
            samples_out.append({
                "id": sid,
                "source": s.get("source", ""),
                "variant": s.get("variant", ""),
                "split": s.get("split", "public"),
                "gt": s.get("gt", []),
            })
        testset_version = f"v{ts.get('version', '?')}-{ts.get('split', 'public')}"
        (pkg / "vad-manifest.json").write_text(json.dumps({
            "version": version,
            "testset_version": testset_version,
            "testset_release_url": settings.VAD_PACKAGE_URL.strip() or self.V31_RELEASE_URL,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "samples": samples_out,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return pkg

    def vad_package_sha256(self, version: int) -> str:
        """Deterministischer Hash des VAD-Pakets (Manifest + je WAV, sortiert)."""
        pkg = self.build_vad_package(version)
        parts = [hashlib.sha256((pkg / "vad-manifest.json").read_bytes()).digest()]
        for wav in sorted((pkg / "audio").glob("*.wav")):
            parts.append(hashlib.sha256(wav.read_bytes()).digest())
        return hashlib.sha256(b"".join(parts)).hexdigest()

    def latest_results(self) -> dict:
        """latest.json inkl. `per_category` (Change 032) + `per_sample` (Change 039).

        Bestehende latest.json-Dateien (vor Change 032 gepoolt) enthalten
        kein `per_category`/`per_sample` — das wird hier on-the-fly aus den
        Run-Rows + aktivem Manifest nachgerüstet (gleiche Formel wie beim
        Re-Pooling: WER/CER gemittelt je (Kategorie × Backend), nur Rows mit
        wer-Wert; per_sample: WER je Backend für genau ein Sample). So
        funktionieren die Kategorie-Charts und Sample-Mini-Tabellen sofort
        nach dem Deploy, ohne auf den nächsten Submit warten zu müssen.
        """
        p = self.data_dir / "results" / "latest.json"
        latest = json.loads(p.read_text(encoding="utf-8"))
        # Change 062/065: VAD-Sektion immer on-the-fly anreichern (auch wenn
        # latest.json vor dem VAD-Deploy gepoolt wurde). Change 065:
        # _vad_summary berechnet den VAD-Paket-Hash selbst.
        try:
            runs_dir = self.data_dir / "results" / "runs"
            if runs_dir.exists():
                latest["vad"] = self._vad_summary(runs_dir)
                # Change 132: Aligner-Benchmark on-the-fly anreichern
                latest["aligner"] = self._aligner_summary(runs_dir)
        except (FileNotFoundError, KeyError):
            latest.setdefault("vad", [])
            latest.setdefault("aligner", [])
        if latest.get("per_category") and latest.get("per_sample"):
            return latest
        try:
            m = self.latest_manifest()
            sha = self.package_sha256(m["version"])
        except (FileNotFoundError, KeyError):
            return latest
        cat_by_id = {s["id"]: s.get("category", "unknown")
                     for s in m.get("samples", [])}
        per_cat: Dict[tuple, list] = {}  # (category, backend) -> [wer_sum, cer_sum, n]
        per_sample: Dict[str, Dict[str, float]] = {}  # sample_id -> {backend: wer}
        runs_dir = self.data_dir / "results" / "runs"
        if not runs_dir.exists():
            return latest
        for rf in runs_dir.glob("*.json"):
            data = json.loads(rf.read_text(encoding="utf-8"))
            if data.get("manifest_sha256") != sha:
                continue
            for r in data["rows"]:
                if r.get("wer") is None:
                    continue
                sid = r.get("sample_id")
                if not sid:
                    continue
                per_sample.setdefault(sid, {})[data["backend"]] = r["wer"]
                cat = cat_by_id.get(sid, "unknown")
                cell = per_cat.setdefault((cat, data["backend"]), [0.0, 0.0, 0])
                cell[0] += r["wer"]
                cell[1] += r.get("cer") or 0.0
                cell[2] += 1
        per_category = [
            {
                "category": cat,
                "backend": bname,
                "wer": round(wsum / n, 4),
                "cer": round(csum / n, 4),
                "n": n,
            }
            for (cat, bname), (wsum, csum, n) in sorted(per_cat.items())
        ]
        latest["per_category"] = per_category
        latest["per_sample"] = {
            sid: {b: round(w, 4) for b, w in backs.items()}
            for sid, backs in sorted(per_sample.items())
        }
        return latest

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

    # ── Selbstbedienung (Change 030): Paket + Hash + Submit ───────────────

    def package_sha256(self, version: Optional[int] = None) -> str:
        """Deterministischer Paket-Hash (REQ-WEB-040).

        sha256 über die Verkettung sha256(manifest.json) + je
        Audio-Datei sha256 (WAVs alphabetisch). Version-gebunden.
        """
        if version is None:
            version = self.latest_manifest()["version"]
        assert version is not None
        vdir = self._version_dir(version)
        mpath = vdir / "manifest.json"
        if not mpath.exists():
            raise FileNotFoundError(f"Version v{version} fehlt (manifest.json)")
        parts = [hashlib.sha256(mpath.read_bytes()).digest()]
        for wav in sorted((vdir / "audio").glob("*.wav")):
            parts.append(hashlib.sha256(wav.read_bytes()).digest())
        return hashlib.sha256(b"".join(parts)).hexdigest()

    # ── Benchmark-Set-Auto-Update (Change 075/076) ────────────────────────

    #: Discovery-Cache (Change 076): (git_url, timestamp) → Liste. ls-remote
    #: ist billig, aber manche Hosts raten-limitieren — Cache 300 s.
    _set_discovery_cache: Dict[str, Any] = {}

    #: Git-Befehlszeilen-Basis (env-überschreibbar für Tests/Container).
    GIT_BIN: str = os.getenv("GIT_BIN", "git")

    @staticmethod
    def _run_git(args: List[str], timeout: int) -> str:
        """Führt git aus: GIT_TERMINAL_PROMPT=0 (kein interaktives Hängen),
        Timeout, wirft RuntimeError bei Fehler."""
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "true"  # keine Credential-Prompts
        try:
            proc = subprocess.run(
                [BenchmarkService.GIT_BIN, *args],
                capture_output=True, text=True, timeout=timeout, env=env,
            )
        except FileNotFoundError:
            raise RuntimeError("git ist nicht installiert (GIT_BIN?)")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git {args[0]} timeout nach {timeout}s")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()
            msg = tail[-1] if tail else "unbekannter git-Fehler"
            raise RuntimeError(f"git {args[0]} fehlgeschlagen: {msg}")
        return proc.stdout

    def set_status(self) -> Dict[str, Any]:
        """Status des Set-Update-Mechanismus (öffentlich, keine Secrets).

        current_version: aktive Version; installed_versions: alle; URL/SHA
        nur als Präfix (SHA 8 Zeichen), auto_install-Flag, letzter Fehler.
        Change 076: `git_url` + `available` (verfügbare Releases, gecacht) +
        `pinning_mode` (true wenn env-URL gesetzt → kein Discovery).
        """
        from app.config import settings

        try:
            cur = self.latest_manifest().get("version")
        except FileNotFoundError:
            cur = None
        sha = settings.BENCHMARK_SET_SHA256.strip()
        git_url = (settings.BENCHMARK_SET_GIT_URL or "").strip()
        pinning = bool(settings.BENCHMARK_SET_URL.strip())
        available: List[Dict[str, Any]] = []
        if git_url and not pinning:
            try:
                available = self.discover_sets(git_url)
            except Exception as e:  # noqa: BLE001 — Status darf nie crashen
                self._set_last_error = f"Discovery fehlgeschlagen: {e}"
        return {
            "mechanism": "benchmark-set",
            "configured": pinning or bool(git_url),
            "pinning_mode": pinning,
            "git_url": git_url,
            "url": settings.BENCHMARK_SET_URL.strip(),
            "sha_prefix": sha[:8] if sha else "",
            "auto_install": settings.BENCHMARK_SET_AUTO_INSTALL,
            "current_version": cur,
            "installed_versions": self.version_numbers(),
            "available": available,
            "last_error": getattr(self, "_set_last_error", None),
        }

    def discover_sets(self, git_url: str) -> List[Dict[str, Any]]:
        """Listet benchmark-set-v<N>-Tags eines Git-Repos (Change 076).

        `git ls-remote --tags <url>` — host-agnostisch (GitHub, GitLab,
        selbst gehostet, lokaler Pfad). Kein GitHub-API-Call.
        Gecacht (300 s). Fehler → RuntimeError mit Meldung.
        """
        git_url = git_url.strip()
        if not git_url:
            raise RuntimeError("keine Git-URL übergeben")
        now = time.time()
        cached = self._set_discovery_cache.get(git_url)
        if cached and now - cached[0] < 300:
            return cached[1]

        try:
            out = self._run_git(["ls-remote", "--tags", git_url], timeout=60)
        except RuntimeError as e:
            raise RuntimeError(f"git ls-remote {git_url[:40]}…: {e}")

        out_list: List[Dict[str, Any]] = []
        for line in out.splitlines():
            # Zeilenformat: "<sha>\trefs/tags/<name>" — Peeled-Annotationen
            # ("^{}") überspringen; Tags, die kein benchmark-set-v<N> sind, filtern.
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            ref = parts[1]
            if ref.endswith("^{}"):
                continue
            m = re.fullmatch(r"refs/tags/benchmark-set-v(\d+)", ref)
            if not m:
                continue
            out_list.append({
                "version": int(m.group(1)),
                "tag": f"benchmark-set-v{m.group(1)}",
            })
        out_list.sort(key=lambda s: s["version"], reverse=True)
        self._set_discovery_cache[git_url] = (time.time(), out_list)
        return out_list

    def _download_bytes(self, url: str, timeout: int = 300) -> bytes:
        """HTTPS-Pflicht-Download (gemeinsamer Helfer für Set-Install)."""
        if not url.lower().startswith("https://"):
            raise RuntimeError(f"URL muss HTTPS sein (bekam {url[:40]}…)")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — Netzwerkfehler → Meldung
            raise RuntimeError(f"Download fehlgeschlagen ({url[:60]}…): {e}")

    @staticmethod
    def _parse_sha_asset(content: bytes) -> str:
        """Erste Hex-Zeichenfolge aus einer .sha256-Datei.

        Unterstützt sha256sum-Format (`<hash>  <filename>`) und nacktes
        `<hash>` — beides verbreitet.
        """
        text = content.decode("utf-8", errors="replace")
        m = re.search(r"([0-9a-fA-F]{64})", text)
        if not m:
            raise RuntimeError(".sha256-Datei enthält keinen SHA256-Hash")
        return m.group(1).lower()

    def install_set_from_release(
        self,
        url: Optional[str] = None,
        expected_sha: Optional[str] = None,
        git_url: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Installiert ein Benchmark-Set (Change 075 + 076).

        Priorität:
        1. `url` (Body-Override) → Pin-Pfad wie Change 075
        2. `BENCHMARK_SET_URL` env → Pin-Pfad
        3. sonst: git-basiert über `git_url` (arg oder BENCHMARK_SET_GIT_URL)
           → Zielversion = `version`-Arg oder neueste; SHA aus `.sha256`-Datei.
        """
        from app.config import settings

        self._set_last_error = None
        url = (url or "").strip() or settings.BENCHMARK_SET_URL.strip()
        if url:
            # Pin-Pfad (Change 075): URL + SHA explizit
            expected_sha = (expected_sha or settings.BENCHMARK_SET_SHA256).strip()
            if not expected_sha:
                self._set_last_error = (
                    "BENCHMARK_SET_SHA256 fehlt — kein Install ohne Verifikation"
                )
                raise RuntimeError(self._set_last_error)
            raw = self._download_bytes(url)
            return self._install_zip_bytes(raw, expected_sha)

        # Git-Pfad (Change 076)
        git_url = (git_url or "").strip() or settings.BENCHMARK_SET_GIT_URL.strip()
        if not git_url:
            self._set_last_error = (
                "Keine Quelle konfiguriert: BENCHMARK_SET_GIT_URL (git) "
                "oder BENCHMARK_SET_URL (Pin) setzen"
            )
            raise RuntimeError(self._set_last_error)
        try:
            sets = self.discover_sets(git_url)
        except RuntimeError as e:
            self._set_last_error = str(e)
            raise
        if not sets:
            self._set_last_error = (
                f"Keine benchmark-set-v<N>-Tags in {git_url[:40]}… gefunden"
            )
            raise RuntimeError(self._set_last_error)
        target = version
        if target is None:
            target = max(s["version"] for s in sets)
        entry = next((s for s in sets if s["version"] == target), None)
        if entry is None:
            self._set_last_error = f"Tag benchmark-set-v{target} nicht gefunden"
            raise RuntimeError(self._set_last_error)

        # git clone --depth 1 --branch <tag> --single-branch → Checkout
        import tempfile

        tag = entry["tag"]
        with tempfile.TemporaryDirectory(prefix="benchmark-set-") as td:
            try:
                self._run_git(
                    ["clone", "--depth", "1", "--branch", tag,
                     "--single-branch", git_url, td],
                    timeout=300,
                )
            except RuntimeError as e:
                self._set_last_error = f"git clone {tag} fehlgeschlagen: {e}"
                raise RuntimeError(self._set_last_error)
            checkout = Path(td)
            zip_path = checkout / f"{tag}.zip"
            sha_path = checkout / f"{tag}.zip.sha256"
            if not zip_path.exists():
                self._set_last_error = (
                    f"{tag}.zip fehlt im Checkout — Repo-Konvention nicht erfüllt"
                )
                raise RuntimeError(self._set_last_error)
            if not sha_path.exists():
                expected_sha = settings.BENCHMARK_SET_SHA256.strip()
            else:
                expected_sha = self._parse_sha_asset(sha_path.read_bytes())
            if not expected_sha:
                self._set_last_error = (
                    f"{tag} hat keine .sha256-Datei und BENCHMARK_SET_SHA256 "
                    "ist nicht gesetzt — kein Install"
                )
                raise RuntimeError(self._set_last_error)
            raw = zip_path.read_bytes()
        return self._install_zip_bytes(raw, expected_sha)

    def _install_zip_bytes(
        self, raw: bytes, expected_sha: str
    ) -> Dict[str, Any]:
        """Kern-Install aus ZIP-Bytes (SHA-verifiziert, sicher entpackt)."""
        import zipfile

        # SHA256
        got = hashlib.sha256(raw).hexdigest()
        if got.lower() != expected_sha.lower():
            self._set_last_error = (
                f"SHA256-Mismatch: erwartet {expected_sha[:12]}…, "
                f"erhalten {got[:12]}… — nichts installiert"
            )
            raise RuntimeError(self._set_last_error)
        # manifest.json lesen (nur das — Rest erst nach Checks entpacken)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = z.namelist()
                manifest_name = "manifest.json"
                if manifest_name not in names:
                    raise KeyError(manifest_name)
                manifest = json.loads(
                    z.read(manifest_name).decode("utf-8")
                )
                new_version = int(manifest["version"])
        except Exception as e:  # noqa: BLE001
            self._set_last_error = f"Release-Paket ungültig: {e}"
            raise RuntimeError(self._set_last_error)
        # Version ≤ aktuell → skip (nie überschreiben)
        try:
            current = self.latest_manifest().get("version")
        except FileNotFoundError:
            current = None
        if current is not None and new_version <= current:
            return {
                "ok": True,
                "skipped": True,
                "reason": "bereits installiert",
                "installed_version": None,
                "current_version": current,
            }
        # Sicher entpacken (nur erlaubte Pfade, sanitized)
        tmp = self._versions_dir() / f".tmp-v{new_version}"
        if tmp.exists():
            shutil.rmtree(tmp)
        (tmp / "audio").mkdir(parents=True, exist_ok=True)
        (tmp / "preview").mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for info in z.infolist():
                    name = info.filename
                    if name.endswith("/"):
                        continue
                    if name == "manifest.json":
                        target = tmp / "manifest.json"
                    elif name.startswith("audio/") and name.lower().endswith(".wav"):
                        target = tmp / "audio" / Path(name).name
                    elif name.startswith("preview/") and name.lower().endswith((".mp3", ".wav")):
                        target = tmp / "preview" / Path(name).name
                    else:
                        raise RuntimeError(f"unerlaubter Zip-Eintrag: {name}")
                    target.write_bytes(z.read(info))
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(tmp, ignore_errors=True)
            self._set_last_error = f"Entpacken abgebrochen: {e}"
            raise RuntimeError(self._set_last_error)
        # Vollständigkeitsprüfung: audio/preview == samples
        n_samples = len(manifest.get("samples", []))
        n_audio = len(list((tmp / "audio").glob("*.wav")))
        n_preview = len(list((tmp / "preview").glob("*")))
        if n_audio < n_samples:
            shutil.rmtree(tmp, ignore_errors=True)
            self._set_last_error = (
                f"Unvollständiges Paket: {n_audio} WAVs für {n_samples} Samples"
            )
            raise RuntimeError(self._set_last_error)
        if n_preview < n_samples:
            shutil.rmtree(tmp, ignore_errors=True)
            self._set_last_error = (
                f"Unvollständiges Paket: {n_preview} Previews für {n_samples} Samples"
            )
            raise RuntimeError(self._set_last_error)
        # supersedes ergänzen, falls fehlend
        if "supersedes" not in manifest or not manifest.get("supersedes"):
            manifest["supersedes"] = current
        (tmp / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Atomic rename → aktiv (höchste Versionsnummer = latest)
        target = self._versions_dir() / f"v{new_version}"
        if target.exists():
            shutil.rmtree(target)
        tmp.replace(target)
        self._set_last_error = None
        return {
            "ok": True,
            "skipped": False,
            "installed_version": new_version,
            "sha256": got,
            "sample_count": n_samples,
            "supersedes": manifest.get("supersedes"),
        }

    def build_package_tarball(self, version: Optional[int] = None) -> bytes:
        """Tarball der Version: manifest.json + audio/*.wav (+ preview/*.mp3).

        Determinismus: Member alphabetisch, mtime=0, keine UID/GID —
        Byte-identische Tarballs über Requests hinweg.
        """
        if version is None:
            version = self.latest_manifest()["version"]
        assert version is not None
        vdir = self._version_dir(version)
        rels = ["manifest.json"]
        rels += sorted(f"audio/{p.name}" for p in (vdir / "audio").glob("*.wav"))
        preview_dir = vdir / "preview"
        if preview_dir.is_dir():
            rels += sorted(f"preview/{p.name}" for p in preview_dir.glob("*.mp3"))
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
            for rel in rels:
                p = vdir / rel
                if not p.is_file():
                    continue
                ti = tar.gettarinfo(str(p), arcname=rel)
                ti.mtime = 0
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ""
                with open(p, "rb") as f:
                    tar.addfile(ti, f)
        return buf.getvalue()

    def apply_submission(self, payload: dict) -> dict:
        """Validiert + persistiert einen Backend-Submit (REQ-WEB-041).

        - manifest_version + manifest_sha256 müssen zur aktuellen Version
          passen (sonst ``ok: False, reason: manifest mismatch``).
        - Backend-Name muss in backends.yaml registriert sein (sonst
          ``unknown backend``).
        - Detail-Zeilen → results/runs/<backend>_<ts>.json; danach
          Re-Pooling von latest.json + pricing.json über alle Runs mit
          aktuellem Hash.
        """
        m = self.latest_manifest()
        version = m["version"]
        kind = payload.get("kind", "asr")
        # Change 062: VAD-Submits validieren gegen das VAD-Paket (eigener
        # Hash), ASR-Submits gegen das ASR-Paket.
        sha = self.vad_package_sha256(version) if kind == "vad" else self.package_sha256(version)
        if (
            payload.get("manifest_version") != version
            or payload.get("manifest_sha256") != sha
        ):
            return {
                "ok": False,
                "reason": "manifest mismatch",
                "current": {"version": version, "sha256": sha},
            }
        backend = payload["backend"]
        kind = payload.get("kind", "asr")
        if kind == "vad":
            # Change 062: VAD-Modelle aus vad_models.yaml (auch lizenz-
            # inkompatible Referenz-Modelle) — getrennt von ASR-Backends.
            from .service_registry import get_vad_model

            if get_vad_model(backend) is None:
                return {"ok": False, "reason": "unknown backend", "backend": backend}
        elif get_service(backend) is None:
            return {"ok": False, "reason": "unknown backend", "backend": backend}

        runs_dir = self.data_dir / "results" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        run_file = runs_dir / f"{backend}_{ts}.json"
        i = 1
        while run_file.exists():
            run_file = runs_dir / f"{backend}_{ts}_{i}.json"
            i += 1
        run = {
            "backend": backend,
            "kind": payload.get("kind", "asr"),
            "settings": payload.get("settings", "auto"),
            "run_id": payload.get("run_id"),
            "generated_at": payload.get("generated_at"),
            "manifest_version": version,
            "manifest_sha256": sha,
            "meta": payload.get("meta", {}),
            "rows": payload.get("rows", []),
        }
        run_file.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

        # ── Re-Pooling über alle Runs mit aktuellem Hash ──────────────────
        by_backend: Dict[str, List[dict]] = {}
        # REQ-BEN-046: Kategorie je Sample aus dem aktiven Manifest mappen
        # (Runner-Rows tragen nur sample_id, keine category).
        cat_by_id = {s["id"]: s.get("category", "unknown")
                     for s in m.get("samples", [])}
        per_cat: Dict[tuple, list] = {}  # (category, backend) -> [wer_sum, cer_sum, n]
        per_sample: Dict[str, Dict[str, float]] = {}  # Change 039
        for rf in runs_dir.glob("*.json"):
            data = json.loads(rf.read_text(encoding="utf-8"))
            # Change 062: VAD-Runs gehören nicht in den ASR-Pool (kein wer)
            if data.get("kind") == "vad" or data.get("manifest_sha256") != sha:
                continue
            bb = by_backend.setdefault(data["backend"], [])
            for r in data["rows"]:
                if r.get("wer") is None:
                    continue
                bb.append(r)
                sid = r.get("sample_id")
                if not sid:
                    continue
                per_sample.setdefault(sid, {})[data["backend"]] = r["wer"]
                cat = cat_by_id.get(sid, "unknown")
                cell = per_cat.setdefault((cat, data["backend"]), [0.0, 0.0, 0])
                cell[0] += r["wer"]
                cell[1] += r.get("cer") or 0.0
                cell[2] += 1

        pooled: List[dict] = []
        for bname, rows in by_backend.items():
            n = len(rows)
            pooled.append({
                "backend": bname,
                "settings": "auto",
                "wer": sum(r["wer"] for r in rows) / n,
                "cer": sum(r.get("cer") or 0 for r in rows) / n,
                "coverage_pct": sum(r.get("coverage_pct") or 0 for r in rows) / n,
                "rtf": sum(r.get("rtf") or 0 for r in rows) / n,
                "n_samples": n,
            })
        pooled.sort(key=lambda r: r["backend"])

        # REQ-BEN-046: Kategorie-Ebene (Kategorie × Backend → WER/CER/n)
        per_category: List[dict] = []
        for (cat, bname), (wsum, csum, n) in sorted(per_cat.items()):
            per_category.append({
                "category": cat,
                "backend": bname,
                "wer": round(wsum / n, 4),
                "cer": round(csum / n, 4),
                "n": n,
            })

        latest = {
            "version": version,
            "run_id": f"pooled-{int(time.time())}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": pooled,
            "per_category": per_category,
            "per_sample": {
                sid: {b: round(w, 4) for b, w in backs.items()}
                for sid, backs in sorted(per_sample.items())
            },
            "vad": self._vad_summary(runs_dir),  # Change 062/065
        }
        (self.data_dir / "results" / "latest.json").write_text(
            json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ── pricing.json (RTF-basiert) ────────────────────────────────────
        pricing_rows = []
        for bname, rows in by_backend.items():
            n = len(rows)
            avg_rtf = sum(r.get("rtf") or 0 for r in rows) / n
            base = BACKEND_COST_ASSUMPTION.get(bname, 0.0002)
            pricing_rows.append({
                "backend": bname,
                "group": "polyschnack",
                "wer": sum(r["wer"] for r in rows) / n,
                "eur_per_min_selfhost": round(base * (1 + avg_rtf), 6),
                "eur_per_min_saas": None,
                "eur_per_min_commercial": None,
            })
        pricing_rows.sort(key=lambda r: r["backend"])
        pricing = {
            "generated_at": latest["generated_at"],
            "note": "Selbstkosten-Annahme (RTF-basiert); SaaS/kommerziell erst nach Freigabe.",
            "rows": pricing_rows,
        }
        (self.data_dir / "pricing.json").write_text(
            json.dumps(pricing, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "ok": True,
            "backend": backend,
            "version": version,
            "sha256": sha,
            "pooled": pooled,
            "runs_file": run_file.name,
        }

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

    # ── VAD-Testset-Samples (Change 073) ──────────────────────────────────

    def _vad_package_dir(self) -> Path:
        """Aktuelles VAD-Paket (Change 065): versions/v{n}/vad/."""
        return self._version_dir(self.latest_manifest()["version"]) / "vad"

    def vad_samples(self) -> List[dict]:
        """Öffentliche VAD-Testset-Liste (Change 073).

        Liest das vad-manifest.json des aktuellen Pakets (235 public
        Samples: CommonVoice + Piper-Basis, DEMAND-SNR-Mixe, Noise/Musik/
        Babble-FP) und ergänzt Preview-/Audio-URLs. Held-out ist nicht im
        Paket — es gibt hier nichts Geheimes.
        """
        manifest = self._vad_package_dir() / "vad-manifest.json"
        if not manifest.exists():
            raise FileNotFoundError("kein VAD-Paket vorhanden")
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
        return [
            {
                "id": s["id"],
                "source": s.get("source", ""),
                "variant": s.get("variant", ""),
                "split": s.get("split", "public"),
                "has_gt": bool(s.get("gt")),
                "preview_url": f"/api/benchmark/vadpreview/{s['id']}",
                "audio_url": f"/api/benchmark/vadaudio/{s['id']}",
            }
            for s in pkg.get("samples", [])
        ]

    def vad_audio_path(self, sample_id: str) -> Path:
        """WAV-Pfad eines VAD-Samples (Change 073)."""
        p = self._vad_package_dir() / "audio" / f"{sample_id}.wav"
        if not p.exists():
            raise KeyError(sample_id)
        return p

    def ensure_vad_preview(self, sample_id: str) -> Path:
        """Preview-MP3 (128k) eines VAD-Samples, on-demand gecacht (Change 073)."""
        dest = self._vad_package_dir() / "preview" / f"{sample_id}.mp3"
        if dest.exists():
            return dest
        src = self.vad_audio_path(sample_id)
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
