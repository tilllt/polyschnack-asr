#!/usr/bin/env python3
"""VAD-Benchmark (Change 060/062) — Engines aus vad_engines.py.

Testset:
  A) DE-Synthese: Piper-TTS-Samples mit deterministischer Stille-Insertion
     (vorne/hinten/beide/mittig) — exakte Ground Truth.
  B) TEN-VAD-Testset (assets/tenvad/testset-audio-*.scv) — offizielle GT.
  C) Noise-FP: weißes Rauschen + DEMAND (Küche/Metro, 30 s) — jede erkannte
     Speech-Zeit ist ein False Positive.

Metriken: Boundary-Fehler (ms), Region-F1, FP-Zeit auf Noise, RTF.
Ausgabe: out/results.md + out/results.json.

Engines (vad_engines.ENGINES): silero_onnx, ten_vad, webrtc, humaware,
speechbrain, energy. Torch-Engines brauchen .venv-torch (README).
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from vad_engines import ENGINES, LICENSES, SR, _regions

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
OUT = HERE / "out"

# ---------------------------------------------------------------- Audio-IO

def load_wav16k(path: Path) -> np.ndarray:
    """WAV → mono float32 [-1,1] @ 16 kHz (ffmpeg für alle Formate)."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32767.0


def save_wav16k(path: Path, wav: np.ndarray) -> None:
    s16 = (np.clip(wav, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(s16.tobytes())


# ------------------------------------------------------------- Testset

def _energy_gt(wav: np.ndarray, window: int = 512, thresh_db: float = -40.0) -> list[tuple[float, float]]:
    """Energie-Regionen (VAD-freie GT-Basis)."""
    probs = np.array([
        1.0 if np.sqrt((wav[i * window:(i + 1) * window] ** 2).mean()) > 10 ** (thresh_db / 20)
        else 0.0
        for i in range((wav.size - window) // window + 1)
    ], dtype=np.float32)
    return _regions(probs, wav.size, window=window, threshold=0.5)


def _shift_mid(seg, mid_at, mid_len):
    s, e = seg
    if e <= mid_at:
        return [(s, e)]
    if s >= mid_at:
        return [(s + mid_len, e + mid_len)]
    return [(s, mid_at), (mid_at + mid_len, e + mid_len)]


def _parse_scv(scv: Path) -> list[tuple[float, float]]:
    """.scv: name,start,end,is_speech,... → Speech-Regionen (Sekunden)."""
    parts = scv.read_text().strip().split(",")[1:]
    regs, cur = [], None
    for i in range(0, len(parts), 3):
        start, end = float(parts[i]), float(parts[i + 1])
        speech = int(parts[i + 2])
        if speech:
            cur = [start, end] if cur is None else [cur[0], end]
        elif cur is not None:
            regs.append(tuple(cur)); cur = None
    if cur is not None:
        regs.append(tuple(cur))
    return regs


def build_testset(out_dir: Path, tts_dir: Path, ten_dir: Path,
                  max_tts: int = 12) -> dict:
    """Erzeugt WAVs + GT. Returns {id: {"file", "gt": [(s,e),...], "kind"}}."""
    manifest = {}
    tts_dir = Path(tts_dir)
    ten_dir = Path(ten_dir)
    samples = sorted(glob.glob(str(tts_dir / "tts_clean_*.wav")))[:max_tts]
    # A) DE-Synthese mit Stille-Insertion
    for si, src in enumerate(samples):
        wav = load_wav16k(Path(src))
        gt = _energy_gt(wav)
        if not gt:
            continue
        dur = wav.size / SR
        variants = [
            ("lead2", 2.0, None),   # 2 s Stille vorne
            ("trail2", 0.0, None),  # 2 s Stille hinten
            ("both2", 2.0, None),   # 2 s vorne + 2 s hinten
        ]
        if dur >= 4.0:
            variants.append(("mid1", 0.0, (1.5, 1.0)))
        for vname, lead, mid in variants:
            if mid is not None:
                mid_at, mid_len = mid
                out_wav = np.concatenate([
                    wav[:int(mid_at * SR)],
                    np.zeros(int(mid_len * SR)),
                    wav[int(mid_at * SR):],
                    np.zeros(int(2.0 * SR)),
                ])
                g = []
                for s, e in gt:
                    g.extend(_shift_mid((s, e), mid_at, mid_len))
            else:
                out_wav = np.concatenate([
                    np.zeros(int(lead * SR)), wav,
                    np.zeros(int((2.0 if vname == "both2" else (2.0 if vname == "trail2" else 0.0)) * SR)),
                ])
                g = [(s + lead, e + lead) for s, e in gt]
            sid = f"de_{si:02d}_{vname}"
            save_wav16k(out_dir / f"{sid}.wav", out_wav)
            manifest[sid] = {"file": str(out_dir / f"{sid}.wav"),
                             "gt": g, "kind": "de_synth"}
    # B) TEN-Testset (eigene GT aus .scv)
    for scv in sorted(glob.glob(str(ten_dir / "testset-audio-*.scv")))[:10]:
        scv = Path(scv)
        stem = scv.stem
        wavf = ten_dir / f"{stem}.wav"
        if not wavf.exists():
            continue
        gt = _parse_scv(scv)
        sid = f"ten_{stem}"
        shutil.copyfile(wavf, out_dir / f"{sid}.wav")
        manifest[sid] = {"file": str(out_dir / f"{sid}.wav"), "gt": gt, "kind": "ten"}
    # C) Noise-FP: weißes Rauschen + DEMAND-Teilmenge (falls vorhanden)
    rng = np.random.default_rng(42)
    for i, dur in enumerate([10.0, 30.0]):
        noise = rng.standard_normal(int(dur * SR)).astype(np.float32) * 0.05
        sid = f"noise_white_{i}"
        save_wav16k(out_dir / f"{sid}.wav", noise)
        manifest[sid] = {"file": str(out_dir / f"{sid}.wav"), "gt": [], "kind": "noise"}
    for wavf in sorted(glob.glob(str(ASSETS / "demand" / "*_sample.wav"))):
        sid = f"noise_demand_{Path(wavf).stem}"
        try:
            w = load_wav16k(Path(wavf))
        except Exception:
            continue
        w = w[: 30 * SR]  # 30 s reichen für den FP-Test
        save_wav16k(out_dir / f"{sid}.wav", w)
        manifest[sid] = {"file": str(out_dir / f"{sid}.wav"), "gt": [], "kind": "noise"}
    return manifest


# -------------------------------------------------------------- Metriken

def _match(preds, gts):
    """Match pred↔gt (max Overlap, IoU > 0.5), restlos für beide Seiten."""
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
            pairs.append((gi, best)); used_p.add(best)
    return pairs, used_p


def evaluate(engine_name, wav, gt, fn) -> dict:
    regs, elapsed = fn(wav)
    dur = wav.size / SR
    rtf = elapsed / dur if dur > 0 else 0.0
    if not gt:  # Noise: jede erkannte Region = FP
        fp_time = sum(e - s for s, e in regs)
        return {"engine": engine_name, "n_gt": 0, "n_pred": len(regs),
                "fp_time": fp_time, "rtf": rtf, "b_start": [], "b_end": [],
                "f1": None}
    pairs, _ = _match(regs, gt)
    b_start = [abs(regs[p][0] - gt[g][0]) * 1000 for g, p in pairs]
    b_end = [abs(regs[p][1] - gt[g][1]) * 1000 for g, p in pairs]
    tp = len(pairs)
    precision = tp / len(regs) if regs else 0.0
    recall = tp / len(gt) if gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"engine": engine_name, "n_gt": len(gt), "n_pred": len(regs),
            "tp": tp, "f1": f1, "b_start": b_start, "b_end": b_end,
            "fp_time": 0.0, "rtf": rtf}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts-dir", default="/opt/data/polyschnack-benchmark/benchmark/data/tts")
    ap.add_argument("--ten-dir", default=str(ASSETS / "tenvad"))
    ap.add_argument("--engines", default="silero_onnx,ten_vad,energy")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--max-tts", type=int, default=12)
    args = ap.parse_args()

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_testset(out_dir, args.tts_dir, args.ten_dir, args.max_tts)
    engines = [e for e in args.engines.split(",") if e]

    agg = {e: {"b_start": [], "b_end": [], "f1": [], "rtf": [],
               "fp_time": 0.0, "fp_secs": 0, "n": 0} for e in engines}
    rows = []
    for sid, meta in manifest.items():
        wav = load_wav16k(Path(meta["file"]))
        for ename in engines:
            res = evaluate(ename, wav, meta["gt"], ENGINES[ename])
            a = agg[ename]
            a["n"] += 1
            a["b_start"].extend(res["b_start"]); a["b_end"].extend(res["b_end"])
            if res["f1"] is not None:
                a["f1"].append(res["f1"])
            a["rtf"].append(res["rtf"])
            if not meta["gt"]:
                a["fp_time"] += res["fp_time"]; a["fp_secs"] += 1
            rows.append({"id": sid, "kind": meta["kind"], **res})

    md = ["# VAD-Benchmark (Change 060/062)", "",
          f"Testset: {len(manifest)} Samples "
          f"({sum(1 for m in manifest.values() if m['kind']=='de_synth')} DE-Synth, "
          f"{sum(1 for m in manifest.values() if m['kind']=='ten')} TEN, "
          f"{sum(1 for m in manifest.values() if m['kind']=='noise')} Noise)", "",
          "| Engine | Lizenz | n | F1 (mean) | B-Start (med ms) | B-Ende (med ms) | FP-Speech (s) | RTF |"]
    md.append("|---|---|---|---|---|---|---|---|")
    for ename in engines:
        a = agg[ename]
        f1m = np.mean(a["f1"]) if a["f1"] else float("nan")
        bs = np.median(a["b_start"]) if a["b_start"] else float("nan")
        be = np.median(a["b_end"]) if a["b_end"] else float("nan")
        fp = a["fp_time"]
        rtf = np.mean(a["rtf"]) if a["rtf"] else float("nan")
        md.append(f"| {ename} | {LICENSES.get(ename, '?')} | {a['n']} | {f1m:.3f} | "
                  f"{bs:.0f} | {be:.0f} | {fp:.1f} | {rtf:.4f} |")
    report = "\n".join(md)
    print(report)
    (out_dir / "results.md").write_text(report)
    (out_dir / "results.json").write_text(json.dumps(
        {"manifest": {k: {kk: vv for kk, vv in v.items() if kk != "file"} for k, v in manifest.items()},
         "agg": {e: {k: (v if k not in ("b_start", "b_end") else None) for k, v in agg[e].items()}
                 for e in engines}}, indent=2, default=str))


if __name__ == "__main__":
    main()
