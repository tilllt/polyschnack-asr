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
import subprocess
import tarfile
import time
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

    def _vad_summary(self, runs_dir: Path, sha: str) -> List[dict]:
        """VAD-Ergebnis-Zusammenfassung (Change 062): je Backend F1/Boundaries/FP/RTF.

        Sammelt Runs mit kind=="vad" + aktuellem Manifest-Hash; ASR-Runs
        (ohne vad_f1) werden ignoriert — der ASR-Pool bleibt unberührt.
        """
        by_backend: Dict[str, List[dict]] = {}
        for rf in runs_dir.glob("*.json"):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("kind") != "vad" or data.get("manifest_sha256") != sha:
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
                "n_samples": n,
                "vad_f1_mean": round(sum(r["vad_f1"] for r in rows) / n, 4),
                "boundary_start_ms_median": _median(bs),
                "boundary_end_ms_median": _median(be),
                "fp_time_s": round(sum(r.get("fp_time_s") or 0 for r in rows), 2),
                "rtf_mean": round(sum(r.get("rtf") or 0 for r in rows) / n, 4),
            })
        out.sort(key=lambda r: r["backend"])
        return out

    # ── VAD-Benchmark-Paket (Change 062) ────────────────────────────────

    def build_vad_package(self, version: int) -> Path:
        """Erzeugt deterministisch das VAD-Paket (Change 062).

        Pro ASR-Sample werden Stille-Insertions-Varianten generiert
        (lead2/trail2/both2/mid1 — gleiche Methodik wie benchmarks/vad);
        die Ground Truth ist die Energie-GT der Quelle + Insertions-Offsets
        (deterministisch, VAD-frei). Gecacht unter versions/v{version}/vad/.
        """
        pkg = self.data_dir / "versions" / f"v{version}" / "vad"
        if (pkg / "vad-manifest.json").exists():
            return pkg
        m = self._load_manifest(version)
        audio_dir = self.data_dir / "versions" / f"v{version}" / "audio"
        pkg.mkdir(parents=True, exist_ok=True)
        out_audio = pkg / "audio"
        out_audio.mkdir(exist_ok=True)
        samples_out: List[dict] = []
        for s in m.get("samples", []):
            src = audio_dir / f"{s['id']}.wav"
            if not src.exists():
                continue
            wav = _wav_to_float16k(src)
            gt = _energy_gt(wav)
            if not gt:
                continue
            dur = wav.size / 16_000
            variants = [("lead2", 2.0, None), ("trail2", 0.0, None), ("both2", 2.0, None)]
            if dur >= 4.0:
                variants.append(("mid1", 0.0, (1.5, 1.0)))
            for vname, lead, mid in variants:
                if mid is not None:
                    mid_at, mid_len = mid
                    out_wav = np.concatenate([
                        wav[: int(mid_at * 16_000)],
                        np.zeros(int(mid_len * 16_000)),
                        wav[int(mid_at * 16_000):],
                        np.zeros(int(2.0 * 16_000)),
                    ])
                    g: List[tuple] = []
                    for seg in gt:
                        g.extend(_shift_mid(seg, mid_at, mid_len))
                else:
                    trail = 2.0 if vname in ("both2", "trail2") else 0.0
                    out_wav = np.concatenate([
                        np.zeros(int(lead * 16_000)), wav,
                        np.zeros(int(trail * 16_000)),
                    ])
                    g = [(seg[0] + lead, seg[1] + lead) for seg in gt]
                sid = f"{s['id']}_{vname}"
                _write_wav16k(out_audio / f"{sid}.wav", out_wav)
                samples_out.append({
                    "id": sid, "source": s["id"], "variant": vname,
                    "gt": [{"start": round(a, 4), "end": round(b, 4)} for a, b in g],
                })
        (pkg / "vad-manifest.json").write_text(json.dumps({
            "version": version,
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
        # Change 062: VAD-Sektion immer on-the-fly anreichern (auch wenn
        # latest.json vor dem VAD-Deploy gepoolt wurde).
        try:
            m = self.latest_manifest()
            sha = self.package_sha256(m["version"])
            runs_dir = self.data_dir / "results" / "runs"
            if runs_dir.exists():
                latest["vad"] = self._vad_summary(runs_dir, sha)
        except (FileNotFoundError, KeyError):
            latest.setdefault("vad", [])
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
            "vad": self._vad_summary(runs_dir, sha),  # Change 062
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


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
