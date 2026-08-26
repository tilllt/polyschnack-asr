#!/usr/bin/env python3
"""PolySchnack Aligner-Benchmark-Runner (Forced-Alignment).

Lässt die 3 Forced-Aligner (qwen3-forced-aligner, TADA, wav2vec2-xlsr-de)
über die Samples des aktiven Benchmark-Manifests laufen (Quellen: cv + tts —
die beiden deutschen Sample-Quellen) und schreibt je Backend einen
Run-JSON (`kind="aligner"`) nach <DATA>/results/runs/ + einen Kreuz-Vergleich
(`kind="aligner_cross"`, paarweises |Δ start|-Median).

MODUS (Change 133): Der Default-Modus spricht die HTTP-API des
aligner-Containers an (`POST /v1/audio/align`, Form-Felder file/text/lang/
method) — derselbe Pfad, den die Webapp nutzt. Damit misst der Benchmark
genau das, was in Produktion läuft (ein Binary, ein Wrapper, 3 Methoden).
`--mode local` nutzt stattdessen die lokalen CLIs (für die Dev-Box ohne
Container).

Metriken je Sample (ohne manuelle GT-Zeiten, pragmatisch):
- n_ref_words   : Wortanzahl des Referenztextes
- n_timed       : Wörter mit gültiger Zeit (start < end)
- n_zero        : Wörter mit start == end (Aligner-Fehler)
- word_coverage_pct : n_timed / n_ref_words * 100  (qwen3-Abbruch → niedrig)
- audio_coverage_pct: letztes Wort-Ende / Audio-Dauer * 100
- rtf           : Laufzeit / Audio-Dauer

Aufruf:
  python3 run_aligner.py --data-dir <BENCHMARK_DATA_DIR> \\
      [--mode http|local] [--sources cv,tts] [--limit N] [--category X] \\
      [--skip <algo>]

HTTP-Modus: ALIGN_URL (Default http://127.0.0.1:5099)
Lokal-Modus: Modell-/Binary-Pfade per Env (Defaults = lokale Dev-Box).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

# ── Konfiguration (Env-Overrides, Defaults = lokale Pfade) ────────────────
ALIGN_URL = os.environ.get("ALIGN_URL", "http://127.0.0.1:5099").rstrip("/")
QWEN3_CLI = os.environ.get("QWEN3_ASR_CLI", "/opt/data/sep-test/qwen3-asr/build/qwen3-asr-cli")
QWEN3_MODEL = os.environ.get(
    "QWEN3_ALIGNER_MODEL", "/opt/data/sep-test/models/qwen3-forced-aligner-0.6b-f16.gguf"
)
CRISPASR = os.environ.get("CRISPASR_BIN", "/opt/data/crispasr-gpu/build-fix/bin/crispasr")
TADA_MODEL = os.environ.get("TADA_MODEL", "/tmp/tada-tts-1b-q4_k.gguf")
TADA_CODEC = os.environ.get("TADA_CODEC", "/tmp/tada-codec-f16.gguf")
# tada-aligner-de.gguf muss neben dem Modell liegen (resolve-Regel: erst
# neben Modell, dann Cache) — Skript prüft und warnt.
TADA_ALIGNER_DE = os.environ.get("TADA_ALIGNER_DE", "/tmp/tada-aligner-de.gguf")
WAV2VEC2_MODEL = os.environ.get(
    "WAV2VEC2_MODEL", "/tmp/wav2vec2-xlsr-de-q4_k.gguf"
)
TIMEOUT_S = int(os.environ.get("ALIGNER_TIMEOUT_S", "600"))

ALIGNERS = ("qwen3", "tada", "wav2vec2")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def package_sha256(data_dir: Path, version: int) -> str:
    """Deterministischer Paket-Hash (identisch zu BenchmarkService.package_sha256):
    sha256(manifest.json) + je Audio-WAV sha256 (alphabetisch)."""
    vdir = data_dir / "versions" / f"v{version}"
    parts = [hashlib.sha256((vdir / "manifest.json").read_bytes()).digest()]
    for wav in sorted((vdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def duration_s(path: Path) -> float:
    """Audio-Dauer via ffprobe."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """Baut multipart/form-data Body + Content-Type (Standardbibliothek, keine Deps)."""
    boundary = f"----alignbench-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n".encode("utf-8")
        )
    for name, (fname, data, ctype) in files.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
            f"filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode("utf-8")
            + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def run_via_http(wav: Path, ref: str, method: str) -> dict:
    """POST /v1/audio/align am aligner-Container (Change 133)."""
    body, ctype = _multipart(
        {"text": ref, "lang": "de", "method": method},
        {"file": (wav.name, wav.read_bytes(), "audio/wav")},
    )
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            f"{ALIGN_URL}/v1/audio/align", data=body,
            headers={"Content-Type": ctype}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        dt = time.monotonic() - t0
        log(f"  ⚠ {method} HTTP-Fehler: {type(exc).__name__}: {exc}")
        return {"words": [], "rtf": dt}
    dt = time.monotonic() - t0
    words = data.get("words", []) if isinstance(data, dict) else []
    return {"words": words, "rtf": dt}


def run_qwen3(wav: Path, ref: str, out_json: Path) -> dict:
    cmd = [
        QWEN3_CLI, "-m", QWEN3_MODEL, "-f", str(wav),
        "--align", "--text", ref, "--lang", "de", "-o", str(out_json),
    ]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    dt = time.monotonic() - t0
    words: list = []
    if r.returncode == 0 and out_json.exists():
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
            words = data.get("words", []) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            words = []
    else:
        log(f"  ⚠ qwen3 RC={r.returncode}: {(r.stderr or r.stdout)[-200:]}")
    return {"words": words, "rtf": dt}


def run_tada(wav: Path, ref: str, out_json: Path) -> dict:
    # Aligner-De neben das Modell legen, falls woanders konfiguriert
    aligner_target = Path(TADA_MODEL).parent / "tada-aligner-de.gguf"
    if Path(TADA_ALIGNER_DE).exists() and not aligner_target.exists():
        aligner_target.write_bytes(Path(TADA_ALIGNER_DE).read_bytes())
    cmd = [
        CRISPASR, "-m", TADA_MODEL, "--codec-model", TADA_CODEC,
        "--source-lang", "de", "--align",
        "--voice", str(wav), "--ref-text", ref,
        "--align-format", "json", "--align-output", str(out_json),
    ]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    dt = time.monotonic() - t0
    words: list = []
    if r.returncode == 0 and out_json.exists():
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
            words = data.get("words", []) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            words = []
    else:
        log(f"  ⚠ tada RC={r.returncode}: {(r.stderr or r.stdout)[-200:]}")
    return {"words": words, "rtf": dt}


def run_wav2vec2(wav: Path, ref: str, out_json: Path) -> dict:
    cmd = [
        CRISPASR, "--align-only", "-am", WAV2VEC2_MODEL,
        "-f", str(wav), "--ref-text", ref,
        "--align-format", "json", "--align-output", str(out_json),
    ]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    dt = time.monotonic() - t0
    words: list = []
    if r.returncode == 0 and out_json.exists():
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
            words = data.get("words", []) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            words = []
    else:
        log(f"  ⚠ wav2vec2 RC={r.returncode}: {(r.stderr or r.stdout)[-200:]}")
    return {"words": words, "rtf": dt}


def make_local_runners() -> dict:
    return {"qwen3": run_qwen3, "tada": run_tada, "wav2vec2": run_wav2vec2}


def compute_metrics(words: list, ref: str, dur: float, rtf: float) -> dict:
    n_ref = len(ref.split()) if ref.strip() else 0
    n_timed = sum(1 for w in words
                  if (w.get("end") or 0) - (w.get("start") or 0) >= 0.001)
    n_zero = len(words) - n_timed
    last_end = max((w.get("end") or 0) for w in words) if words else 0.0
    word_cov = (n_timed / n_ref * 100.0) if n_ref else 0.0
    audio_cov = (last_end / dur * 100.0) if dur > 0 else 0.0
    return {
        "n_ref_words": n_ref,
        "n_timed": n_timed,
        "n_zero": n_zero,
        "last_end_s": round(last_end, 3),
        "word_coverage_pct": round(word_cov, 1),
        "audio_coverage_pct": round(audio_cov, 1),
        "rtf": round(rtf, 3),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Aligner-Benchmark-Runner")
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="BENCHMARK_DATA_DIR (mit versions/, results/)")
    ap.add_argument("--mode", default="http", choices=("http", "local"),
                    help="http = aligner-Container-API (Default, Change 133), "
                         "local = lokale CLIs")
    ap.add_argument("--sources", default="cv,tts",
                    help="Quellen (default: cv,tts = die beiden deutschen Quellen)")
    ap.add_argument("--limit", type=int, default=0, help="nur N Samples (0=alle)")
    ap.add_argument("--category", default="", help="nur eine Kategorie")
    ap.add_argument("--skip", default="", help="kommagetrennte Aligner überspringen")
    args = ap.parse_args()

    if args.mode == "http":
        runners = {a: run_via_http for a in ALIGNERS}
        log(f"Modus: HTTP → {ALIGN_URL} (aligner-Container)")
    else:
        runners = make_local_runners()
        log("Modus: lokal (CLIs)")

    data_dir = args.data_dir
    results_dir = data_dir / "results" / "runs"
    results_dir.mkdir(parents=True, exist_ok=True)

    m = json.loads((data_dir / "versions" / "v1" / "manifest.json")
                   .read_text(encoding="utf-8"))
    version = m["version"]
    sha = package_sha256(data_dir, version)
    log(f"Manifest v{version}: {len(m['samples'])} Samples · sha256 {sha[:12]}…")

    sources = {s.strip() for s in args.sources.split(",")}
    samples = [s for s in m["samples"]
               if s.get("quelle") in sources
               and (not args.category or s.get("category") == args.category)]
    if args.limit:
        samples = samples[: args.limit]
    log(f"Samples (Quellen {sorted(sources)}): {len(samples)}")

    active = [a for a in ALIGNERS if a not in {x.strip() for x in args.skip.split(",")}]
    log(f"Aligner: {', '.join(active)}")

    # ── Läufe ─────────────────────────────────────────────────────────────
    per_backend: dict[str, list] = {a: [] for a in active}
    per_sample_words: dict[str, dict[str, list]] = {}

    for s in samples:
        sid = s["id"]
        wav = data_dir / "versions" / f"v{version}" / "audio" / f"{sid}.wav"
        if not wav.exists():
            log(f"  SKIP {sid}: {wav} fehlt")
            continue
        ref = s.get("text", "")
        dur = duration_s(wav)
        log(f"  {sid} ({s.get('quelle')}/{s.get('category')}, {dur:.1f}s, "
            f"{len(ref.split())} Wörter)")
        per_sample_words[sid] = {}
        for algo in active:
            out_json = results_dir / f"_tmp_{algo}_{sid}.json"
            try:
                if args.mode == "http":
                    # HTTP-API (Change 133): kein lokales out_json nötig
                    res = run_via_http(wav, ref, algo)
                else:
                    res = runners[algo](wav, ref, out_json)
            except subprocess.TimeoutExpired:
                log(f"    ⚠ {algo} TIMEOUT")
                res = {"words": [], "rtf": float("nan")}
            except FileNotFoundError as e:
                log(f"    ⚠ {algo} FEHLT: {e}")
                sys.exit(2)
            finally:
                out_json.unlink(missing_ok=True)
            words = res["words"]
            per_sample_words[sid][algo] = words
            row = {
                "sample_id": sid,
                "category": s.get("category", ""),
                "quelle": s.get("quelle", ""),
                **compute_metrics(words, ref, dur, res["rtf"]),
            }
            per_backend[algo].append(row)
            log(f"    {algo}: {row['n_timed']}/{row['n_ref_words']} Wörter "
                f"({row['word_coverage_pct']}%), 0-Dauer {row['n_zero']}")

    # ── Run-JSONs schreiben (kind="aligner") ───────────────────────────────
    ts = time.strftime("%Y%m%d_%H%M%S")
    for algo, rows in per_backend.items():
        if not rows:
            continue
        run = {
            "kind": "aligner",
            "backend": algo,
            "manifest_sha256": sha,
            "run_id": f"aligner-{algo}-{ts}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sources": sorted(sources),
            "rows": rows,
        }
        out = results_dir / f"aligner_{algo}_{ts}.json"
        out.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"→ {out.name} ({len(rows)} Rows)")

    # ── Kreuz-Vergleich (kind="aligner_cross") ─────────────────────────────
    cross_rows = []
    pairs = [("qwen3", "tada"), ("qwen3", "wav2vec2"), ("tada", "wav2vec2")]
    for a, b in pairs:
        if a not in active or b not in active:
            continue
        deltas: list[float] = []
        for sid, words_by in per_sample_words.items():
            wa, wb = words_by.get(a, []), words_by.get(b, [])
            # index-weise über Wörter mit gleichem Text vergleichen
            for i in range(min(len(wa), len(wb))):
                if wa[i].get("word") != wb[i].get("word"):
                    continue
                sa, sb = wa[i].get("start"), wb[i].get("start")
                if sa is not None and sb is not None:
                    deltas.append(abs(float(sa) - float(sb)))
        if deltas:
            deltas.sort()
            med = deltas[len(deltas) // 2]
            cross_rows.append({
                "pair": f"{a}↔{b}",
                "n_words": len(deltas),
                "delta_ms_median": round(med * 1000, 1),
                "delta_ms_mean": round(sum(deltas) / len(deltas) * 1000, 1),
            })
    if cross_rows:
        cross = {
            "kind": "aligner_cross",
            "manifest_sha256": sha,
            "run_id": f"aligner-cross-{ts}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": cross_rows,
        }
        out = results_dir / f"aligner_cross_{ts}.json"
        out.write_text(json.dumps(cross, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"→ {out.name} (Kreuz-Δ: " +
            ", ".join(f"{r['pair']} {r['delta_ms_median']} ms" for r in cross_rows) + ")")

    log("FERTIG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
