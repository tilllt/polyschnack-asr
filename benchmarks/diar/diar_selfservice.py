#!/usr/bin/env python3
"""Change 136: Diar-Self-Service — Testset holen, Calls messen, submiten.

Analog vad_selfservice.py:

  1. GET {submit}/api/benchmark/diarpackage/sha256 → {version, sha256}
  2. Paket (WAVs + diar-manifest.json) lokal cachen / von der Webapp laden
  3. Pro Call: Segmente via diar-Service (foxnose/pyannote/vad-turns),
     DER/Jaccard/Sprecherzahl/RTF gegen die exakte GT (diar_metrics)
  4. POST {submit}/api/benchmark/submit mit kind="diar" + diar-sha

Exit-Codes: 0 = ok, 2 = Dienst nicht erreichbar/Fehler, 3 = Hash-Mismatch,
            4 = Submit-Fehler.

Beispiel (Container):
  diar_selfservice.py --submit https://whisper.cia-spandau.de \
      --method foxnose --backend crispr-diar-foxnose
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

from diar_metrics import der, jaccard_per_segment, speaker_count_error
from diar_run import diarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("diar-selfservice")

_TIMEOUT = httpx.Timeout(1800.0, connect=30.0)


def package_hash_of(workdir: Path) -> str:
    """sha256(diar-manifest.json) + je WAV (sortiert) — wie der Server."""
    mpath = workdir / "diar-manifest.json"
    parts = [hashlib.sha256(mpath.read_bytes()).digest()]
    for wav in sorted((workdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def fetch_package(client: httpx.Client, submit: str, workdir: Path,
                  sha: str, version: int) -> Path:
    pkg = workdir / f"diar-v{version}"
    if pkg.exists() and (pkg / "diar-manifest.json").exists():
        try:
            if package_hash_of(pkg) == sha:
                log.info("Lokales Diar-Paket v%s passt (sha %s…)", version, sha[:12])
                return pkg
        except OSError:
            pass
    r = client.get(f"{submit.rstrip('/')}/api/benchmark/diarpackage")
    r.raise_for_status()
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        tar.extractall(pkg, filter="data")
    log.info("Diar-Paket v%s geladen: %d Calls laut diar-manifest", version,
             len(json.loads((pkg / "diar-manifest.json").read_text(encoding="utf-8"))["calls"]))
    return pkg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", required=True, help="Webapp-Origin (https://…)")
    ap.add_argument("--method", default=os.environ.get("DIARIZE_METHOD", "foxnose"),
                    help="Methode: foxnose|pyannote|vad-turns (Default: DIARIZE_METHOD)")
    ap.add_argument("--backend", default="",
                    help="Backend-Name in diar_models.yaml (Default: crispr-diar-<method>)")
    ap.add_argument("--diar-url", default=os.environ.get("DIAR_URL", "http://localhost:5098"),
                    help="diar-Service-URL")
    ap.add_argument("--workdir", default="/tmp/diarbench")
    ap.add_argument("--no-submit", action="store_true", help="nur messen, nicht submitten")
    args = ap.parse_args()

    method = args.method
    if method not in ("foxnose", "pyannote", "vad-turns"):
        log.error("Unbekannte Methode '%s'. Verfügbar: foxnose, pyannote, vad-turns", method)
        return 2
    backend = args.backend or f"crispr-diar-{method}"

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
            meta = client.get(f"{submit}/api/benchmark/diarpackage/sha256")
            meta.raise_for_status()
        except httpx.HTTPError:
            log.exception("Diar-Paket-Meta nicht erreichbar")
            return 2
        d = meta.json()
        version, sha = d["version"], d["sha256"]
        pkg = fetch_package(client, submit, workdir, sha, version)

        manifest = json.loads((pkg / "diar-manifest.json").read_text(encoding="utf-8"))
        rows = []
        for call in manifest["calls"]:
            wav = pkg / "audio" / f"{call['id']}.wav"
            gt = [(g["start"], g["end"], g["speaker"]) for g in call["gt"]]
            dur = call["duration_s"]
            try:
                segments, infer_s = diarize(str(wav), method, args.diar_url)
            except (RuntimeError, httpx.HTTPError) as e:
                log.warning("Call %s fehlgeschlagen: %s", call["id"], e)
                continue
            hyp = [(s["start"], s["end"], s["speaker"]) for s in segments]
            der_val, detail = der(gt, hyp)
            row = {
                "sample_id": call["id"],
                "der": der_val,
                "jaccard": jaccard_per_segment(gt, hyp),
                "speaker_count_error": speaker_count_error(gt, hyp),
                "rtf": round(infer_s / dur, 4) if dur > 0 else 0.0,
                "n_gt_speakers": detail["n_gt_speakers"],
                "n_hyp_speakers": detail["n_hyp_speakers"],
            }
            rows.append(row)
            log.info("  %s: DER=%.3f Jaccard=%.3f spk-Fehler=%d RTF=%.3f",
                     call["id"], row["der"], row["jaccard"],
                     row["speaker_count_error"], row["rtf"])

        ders = [r["der"] for r in rows]
        log.info("Gemessen: %d Calls, %d ok — DER-Mittel %.3f",
                 len(manifest["calls"]), len(rows),
                 sum(ders) / len(ders) if ders else 0.0)

        if args.no_submit:
            (workdir / "diar_results.json").write_text(
                json.dumps({"backend": backend, "method": method, "rows": rows}, indent=2))
            return 0

        body = {
            "backend": backend,
            "kind": "diar",
            "settings": "auto",
            "manifest_version": version,
            "manifest_sha256": sha,
            "run_id": f"diar-{method}-{int(time.time())}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": rows,
            "meta": {"method": method, "diar_models_yaml": True},
        }
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        sig = hmac.new(api_key.encode(), raw, hashlib.sha256).hexdigest()
        try:
            r = client.post(f"{submit}/api/benchmark/submit", content=raw,
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
