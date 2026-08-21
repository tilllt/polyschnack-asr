#!/usr/bin/env python3
"""VAD-Self-Service (Change 062): ein VAD-Container holt sich das VAD-Paket
selbst, misst Regionen gegen die exakte GT und submitet die Ergebnisse.

Ablauf:
  1. GET {submit}/api/benchmark/vadpackage/sha256 → {version, sha256}
  2. Lokales Paket (workdir/vad-v{version}) + Hash passt? → wiederverwenden.
     Sonst GET /api/benchmark/vadpackage → Tarball entpacken.
  3. Pro Sample: Regionen berechnen (Engine aus vad_engines, VAD_ENGINE env
     oder --engine); Metriken gegen vad-manifest.json-GT:
     Boundary-Fehler (ms), Region-F1 (IoU>0.5), FP-Zeit (Noise), RTF.
  4. POST {submit}/api/benchmark/submit mit kind="vad" + vad-sha.

Exit-Codes: 0 = ok, 2 = Backend nicht erreichbar, 3 = Hash-Mismatch (409),
            4 = Abbruch durch Timeout/Fehler.

Beispiel (im Container):
  vad_selfservice.py --submit https://whisper.cia-spandau.de \
      --engine silero_onnx --backend silero-onnx
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import logging
import os
import sys
import tarfile
import time
from pathlib import Path

import httpx

from vad_engines import ENGINES, SR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vad-selfservice")

_TIMEOUT = httpx.Timeout(600.0, connect=30.0)


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def package_hash_of(workdir: Path) -> str:
    """sha256(vad-manifest.json) + je WAV (sortiert) — wie der Server."""
    mpath = workdir / "vad-manifest.json"
    parts = [hashlib.sha256(mpath.read_bytes()).digest()]
    for wav in sorted((workdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def fetch_package(client: httpx.Client, submit: str, workdir: Path,
                  sha: str, version: int) -> Path:
    pkg = workdir / f"vad-v{version}"
    if pkg.exists() and (pkg / "vad-manifest.json").exists():
        try:
            if package_hash_of(pkg) == sha:
                log.info("Lokales VAD-Paket v%s passt (sha %s…)", version, sha[:12])
                return pkg
        except OSError:
            pass
    r = client.get(f"{submit.rstrip('/')}/api/benchmark/vadpackage")
    r.raise_for_status()
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        tar.extractall(pkg, filter="data")
    log.info("VAD-Paket v%s geladen: %d Samples laut vad-manifest", version,
             len(json.loads((pkg / "vad-manifest.json").read_text(encoding="utf-8"))["samples"]))
    return pkg


def load_wav16k(path: Path):
    import subprocess

    import numpy as np

    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32767.0


def match(preds, gts):
    """Match pred↔gt (max Overlap, IoU > 0.5)."""
    pairs, used_p = [], set()
    for gi, (gs, ge) in enumerate(gts):
        best, best_iou = None, 0.0
        for pi, (ps, pe) in enumerate(preds):
            if pi in used_p:
                continue
            inter = max(0.0, min(ge, pe) - max(gs, ps))
            union = max(ge, pe) - min(gs, ps)
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou, best = iou, pi
        if best is not None and best_iou > 0.5:
            pairs.append((gi, best))
            used_p.add(best)
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", required=True, help="Webapp-Origin (https://…)")
    ap.add_argument("--backend", default=os.environ.get("VAD_BACKEND", ""),
                    help="VAD-Modell-Name in vad_models.yaml (Default: VAD_BACKEND env)")
    ap.add_argument("--engine", default=os.environ.get("VAD_ENGINE", ""),
                    help="Engine in vad_engines (Default: VAD_ENGINE env)")
    ap.add_argument("--workdir", default="/tmp/vadbench")
    ap.add_argument("--no-submit", action="store_true", help="nur messen, nicht submitten")
    args = ap.parse_args()

    backend = args.backend
    engine = args.engine
    if not backend or not engine:
        log.error("VAD_BACKEND und VAD_ENGINE müssen gesetzt sein (env oder Flags)")
        return 2
    if engine not in ENGINES:
        log.error("Unbekannte Engine '%s'. Verfügbar: %s", engine, ", ".join(ENGINES))
        return 2

    api_key = os.environ.get("BENCHMARK_API_KEY", "").strip()
    if not api_key:
        log.error("BENCHMARK_API_KEY nicht gesetzt — Abbruch")
        return 2

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    submit = args.submit.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}

    with httpx.Client(timeout=_TIMEOUT, headers=headers) as client:
        try:
            meta = client.get(f"{submit}/api/benchmark/vadpackage/sha256")
            meta.raise_for_status()
        except httpx.HTTPError:
            log.exception("VAD-Paket-Meta nicht erreichbar")
            return 2
        d = meta.json()
        version, sha = d["version"], d["sha256"]
        pkg = fetch_package(client, submit, workdir, sha, version)

        manifest = json.loads((pkg / "vad-manifest.json").read_text(encoding="utf-8"))
        rows = []
        for s in manifest["samples"]:
            wav = load_wav16k(pkg / "audio" / f"{s['id']}.wav")
            gt = [(g["start"], g["end"]) for g in s["gt"]]
            t0 = time.perf_counter()
            regs, infer = ENGINES[engine](wav)
            dur = wav.size / SR
            row = {"sample_id": s["id"], "rtf": round(infer / dur, 6)}
            if not gt:  # Noise: jede erkannte Region = FP
                row["fp_time_s"] = round(sum(e - ss for ss, e in regs), 3)
            else:
                pairs = match(regs, gt)
                tp = len(pairs)
                precision = tp / len(regs) if regs else 0.0
                recall = tp / len(gt) if gt else 0.0
                f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
                b_start = [abs(regs[p][0] - gt[g][0]) * 1000 for g, p in pairs]
                b_end = [abs(regs[p][1] - gt[g][1]) * 1000 for g, p in pairs]
                row.update({
                    "vad_f1": round(f1, 4),
                    "boundary_start_ms": round(_median(b_start), 1),
                    "boundary_end_ms": round(_median(b_end), 1),
                    "fp_time_s": 0.0,
                })
            rows.append(row)

        f1s = [r["vad_f1"] for r in rows if "vad_f1" in r]
        log.info("Gemessen: %d Samples, %d mit GT — F1-Mittel %.3f",
                 len(rows), len(f1s), sum(f1s) / len(f1s) if f1s else 0.0)

        if args.no_submit:
            (workdir / "vad_results.json").write_text(
                json.dumps({"backend": backend, "engine": engine, "rows": rows}, indent=2))
            return 0

        body = {
            "backend": backend,
            "kind": "vad",
            "settings": "auto",
            "manifest_version": version,
            "manifest_sha256": sha,
            "run_id": f"vad-{engine}-{int(time.time())}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": rows,
            "meta": {"engine": engine, "vad_models_yaml": True},
        }
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        sig = hmac.new(api_key.encode(), raw, hashlib.sha256).hexdigest()
        try:
            r = client.post(
                f"{submit}/api/benchmark/submit", content=raw,
                headers={"Content-Type": "application/json",
                         "X-Benchmark-Signature": sig})
        except httpx.HTTPError:
            log.exception("Submit fehlgeschlagen")
            return 4
        if r.status_code == 409:
            log.error("Manifest-Mismatch: %s", r.text[:300])
            return 3
        if r.status_code != 200:
            log.error("Submit abgelehnt (%s): %s", r.status_code, r.text[:300])
            return 4
        log.info("Submit ok: %s", r.json())
        return 0


if __name__ == "__main__":
    sys.exit(main())
