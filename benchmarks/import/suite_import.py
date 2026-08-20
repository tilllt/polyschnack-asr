#!/usr/bin/env python3
"""suite_import.py — Helfer für den hash-gesicherten Benchmark-Suite-Import (Change 036).

Läuft auf der Box (nur stdlib). Funktionen:
- compute_package_sha(benchmark_dir, version)  -> package_sha256 (identisch zu
  BenchmarkService.package_sha256: sha256(manifest.json) + sha256(je WAV sortiert))
- latest_version(benchmark_dir)                -> höchste versions/vN-Nummer
- prepare_package(src_dir, benchmark_dir, api_version=None)
  -> spielt versions/vN ein (N = max+1, supersedes = aktive Version), passt das
     Manifest an (version/supersedes), berechnet den FINALEN Hash neu, schreibt
     sha256.txt neu. Gibt (version, sha) zurück. Idempotent.
- build_payload(result_json, version, sha)     -> Submit-Payload (rows aus
  wer_per_sample, rtf = globaler RTF je Row, meta aus instance/gpu/region)
- submit(payload, api_url, key)                -> HMAC-SHA256 signiert POSTen
"""
import hashlib
import hmac
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path


def compute_package_sha(vdir: Path) -> str:
    mpath = vdir / "manifest.json"
    if not mpath.exists():
        raise FileNotFoundError(f"manifest.json fehlt in {vdir}")
    parts = [hashlib.sha256(mpath.read_bytes()).digest()]
    for wav in sorted((vdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def latest_version(benchmark_dir: Path) -> int:
    vdir = benchmark_dir / "versions"
    nums = [int(p.name[1:]) for p in vdir.glob("v[0-9]*") if p.is_dir()]
    return max(nums) if nums else 0


def wav_fingerprint(vdir: Path) -> str:
    """sha256 über Dateinamen + Inhalt aller WAVs — unabhängig vom Manifest.

    Der package_sha256 hängt auch am Manifest (version/supersedes werden beim
    Einspielen finalisiert). Für die Idempotenz zählt aber nur die Daten-
    grundlage: Sind alle WAVs identisch, ist die Suite bereits eingespielt —
    dann laufen nur noch die Results (mit der finalisierten IST-SHA)."""
    h = hashlib.sha256()
    for wav in sorted((vdir / "audio").glob("*.wav")):
        h.update(wav.name.encode("utf-8"))
        h.update(wav.read_bytes())
    return h.hexdigest()


def prepare_package(src_dir: Path, benchmark_dir: Path) -> tuple:
    """Paket (entpacktes versions/vN) einspielen; gibt (version, sha) zurück."""
    src_versions = src_dir / "versions"
    src_v = sorted(src_versions.glob("v[0-9]*"))[0]
    new_num = latest_version(benchmark_dir) + 1

    # Manifest finalisieren: version + supersedes (-> Hash ändert sich!)
    mpath = src_v / "manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    active = latest_version(benchmark_dir)
    m["version"] = new_num
    m["supersedes"] = active if active else None
    mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dest = benchmark_dir / "versions" / f"v{new_num}"
    if dest.exists():
        print(f"FEHLER: Zielversion {dest} existiert bereits — abbrechen (nichts überschrieben)")
        sys.exit(2)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_v, dest)
    sha = compute_package_sha(dest)
    (src_dir / "sha256.txt").write_text(sha + "\n", encoding="utf-8")
    print(f"Version v{new_num} eingespielt (supersedes={active}, {len(list((dest/'audio').glob('*.wav')))} WAVs)")
    print(f"package_sha256 (final): {sha}")
    return new_num, sha


def build_payload(result: dict, version: int, sha: str) -> dict:
    wps = result.get("wer_per_sample", {})
    rows = []
    for sid in sorted(wps):
        wer = wps[sid]
        # vast-Result-JSONs: wer_per_sample[sid] = {"wer": x, "hypothesis": "…"}
        if isinstance(wer, dict):
            wer = wer.get("wer")
        if wer is None:
            continue
        rows.append({
            "sample_id": sid,
            "wer": round(float(wer), 4),
            "rtf": round(float(result.get("rtf", 0.0)), 4),
        })
    meta = {
        "gpu": result.get("gpu"),
        "region": result.get("region"),
        "price_usd_h": result.get("price_usd_h"),
        "instance": result.get("instance"),
        "model_start_s": result.get("model_start_s"),
        "audio_s": result.get("audio_s"),
        "transcribe_wall_s": result.get("transcribe_wall_s"),
    }
    return {
        "backend": result["backend"],
        "settings": "vast-207er-suite",
        "run_id": f"vast-{result['backend']}-{hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:12]}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_version": version,
        "manifest_sha256": sha,
        "meta": meta,
        "rows": rows,
    }


def submit(payload: dict, api_url: str, key: str, runs_dir: Path = None) -> dict:
    """Idempotent: überspringt, wenn eine Run-Datei mit derselben run_id existiert."""
    if runs_dir is not None:
        rid = payload.get("run_id")
        if rid:
            for rf in runs_dir.glob("*.json"):
                try:
                    if json.loads(rf.read_text(encoding="utf-8")).get("run_id") == rid:
                        return {"ok": True, "skipped": True, "run_id": rid}
                except Exception:
                    pass
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        api_url.rstrip("/") + "/api/benchmark/submit",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-Benchmark-Signature": sig,
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    # CLI: suite_import.py <cmd> <args...>
    cmd = sys.argv[1]
    if cmd == "compute-sha":
        print(compute_package_sha(Path(sys.argv[2])))
    elif cmd == "latest-version":
        print(latest_version(Path(sys.argv[2])))
    elif cmd == "wav-fingerprint":
        print(wav_fingerprint(Path(sys.argv[2])))
    elif cmd == "prepare":
        v, s = prepare_package(Path(sys.argv[2]), Path(sys.argv[3]))
        print(f"VERSION={v}\nSHA={s}")
