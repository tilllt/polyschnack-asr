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
        # A2) SNR-Mix (Change 062): clean-Speech + DEMAND-Noise bei 0/5/10 dB.
        #     GT bleibt die Energie-GT des CLEAN-Signals (Noise verfälscht
        #     die Energie-GT sonst — genau das ist der zu messende Fall).
        noise_srcs = sorted(glob.glob(str(ASSETS / "demand" / "*_sample.wav")))[:2]
        if noise_srcs and si < 6:
            noise = load_wav16k(Path(noise_srcs[si % len(noise_srcs)]))
            speech_rms = float(np.sqrt((wav ** 2).mean())) or 1e-9
            for snr_db in (10, 5, 0):
                target_noise_rms = speech_rms * 10 ** (-snr_db / 20)
                n = min(wav.size, noise.size)
                mix = wav[:n] + noise[:n] * (target_noise_rms / (float(np.sqrt((noise[:n] ** 2).mean())) or 1e-9))
                mix = np.clip(mix, -1, 1).astype(np.float32)
                sid = f"de_{si:02d}_snr{snr_db}"
                save_wav16k(out_dir / f"{sid}.wav", mix)
                manifest[sid] = {"file": str(out_dir / f"{sid}.wav"),
                                 "gt": list(gt), "kind": "de_snr"}
    # A3) Babble (Change 062): Ziel-Sprache A + Stör-Sprache B (RMS-gleich,
    #     1,2 s versetzt) — B-Detektionen außerhalb A = Precision-Verlust.
    if len(samples) >= 2:
        a = load_wav16k(Path(samples[0]))
        b = load_wav16k(Path(samples[1]))
        b = b * (float(np.sqrt((a ** 2).mean())) / (float(np.sqrt((b ** 2).mean())) or 1e-9))
        n = min(a.size, b.size + int(1.2 * SR))
        out = np.zeros(n, dtype=np.float32)
        out[:a.size] += a
        out[int(1.2 * SR): int(1.2 * SR) + b.size] += b[:n - int(1.2 * SR)] if n > int(1.2 * SR) else b
        out = np.clip(out, -1, 1).astype(np.float32)
        g = _energy_gt(a)
        sid = "babble_2spk"
        save_wav16k(out_dir / f"{sid}.wav", out)
        manifest[sid] = {"file": str(out_dir / f"{sid}.wav"), "gt": g, "kind": "babble"}
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
    # D) Musik-FP (Change 062): MUSAN-Music — Musik ist keine Sprache,
    #    jede erkannte Speech-Zeit ist ein False Positive.
    for wavf in sorted(glob.glob(str(ASSETS / "musan" / "music" / "*.wav"))):
        sid = f"music_{Path(wavf).stem}"
        try:
            w = load_wav16k(Path(wavf))
        except Exception:
            continue
        w = w[: 30 * SR]
        save_wav16k(out_dir / f"{sid}.wav", w)
        manifest[sid] = {"file": str(out_dir / f"{sid}.wav"), "gt": [], "kind": "music"}
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
    ap.add_argument("--v3", action="store_true",
                    help="V3-Testset nutzen (assets/v3/testset.json + audio/, Change 063)")
    ap.add_argument("--split", choices=["public", "heldout", "all"], default="all",
                    help="Welchen Split messen (Change 064). heldout NUR lokal "
                         "(assets/v3-heldout/) — wird nie vom Release geladen.")
    args = ap.parse_args()

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    if args.v3:
        # V3.1-Testset (Change 063/064): testset.json + audio/ — deterministisch,
        # offiziell als GitHub-Release (tilllt/vad-benchmark-data).
        # Split-Trennung (Change 064): public → Release/Download-Fallback;
        # heldout → NUR lokal, kein Download, sonst Abbruch (Leakage-Schutz).
        load_splits = ["public", "heldout"] if args.split == "all" else [args.split]
        manifest: dict = {}
        for split in load_splits:
            split_dir = ASSETS / ("v3" if split == "public" else "v3-heldout")
            if not (split_dir / "testset.json").exists():
                if split == "heldout":
                    raise SystemExit(
                        "heldout-Testset fehlt lokal (assets/v3-heldout/) — "
                        "held-out-Samples werden nie öffentlich verteilt. "
                        "Lokal generieren: build_testset_v3.py --split heldout")
                import io
                import tarfile
                import urllib.request

                url = ("https://github.com/tilllt/vad-benchmark-data/releases/"
                       "download/v5/vad-testset-v4-public.tar.gz")
                print(f"Lade V4-public-Testset von {url} …")
                with urllib.request.urlopen(url, timeout=120) as r:
                    raw = r.read()
                with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                    tar.extractall(split_dir, filter="data")
                print("V3.1-public-Testset entpackt nach", split_dir)
            ts = json.loads((split_dir / "testset.json").read_text(encoding="utf-8"))
            for s in ts["samples"]:
                manifest[s["id"]] = {
                    "file": str(split_dir / "audio" / f"{s['id']}.wav"),
                    "gt": [(g["start"], g["end"]) for g in s.get("gt", [])],
                    "kind": s.get("kind", "?"),
                    "split": s.get("split", split),
                }
    else:
        manifest = build_testset(out_dir, args.tts_dir, args.ten_dir, args.max_tts)
    engines = [e for e in args.engines.split(",") if e]

    def run_bench(manifest: dict, label: str) -> None:
        """Misst alle Engines auf manifest, schreibt out/results_v3_<label>.{md,json}."""
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
                rows.append({"id": sid, "kind": meta["kind"],
                             "split": meta.get("split", label), **res})

        def cnt(kind):
            return sum(1 for m in manifest.values() if m["kind"] == kind)

        md = ["# VAD-Benchmark (Change 060/062) — Split: " + label, "",
              f"Testset: {len(manifest)} Samples "
              f"({cnt('de_synth')} DE-Synth, {cnt('de_snr')} SNR-Mix, "
              f"{cnt('babble')} Babble, {cnt('ten')} TEN, "
              f"{cnt('noise')} Noise, {cnt('music')} Musik)", "",
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
        (out_dir / f"results_v3_{label}.md").write_text(report)
        (out_dir / f"results_v3_{label}.json").write_text(json.dumps(
            {"manifest": {k: {kk: vv for kk, vv in v.items() if kk != "file"}
                           for k, v in manifest.items()},
             "agg": {e: {k: (v if k not in ("b_start", "b_end") else None)
                         for k, v in agg[e].items()}
                     for e in engines}}, indent=2, default=str))

    if args.v3 and args.split == "all":
        pub = {k: v for k, v in manifest.items() if v.get("split") == "public"}
        ho = {k: v for k, v in manifest.items() if v.get("split") == "heldout"}
        print(f"\n── Split public: {len(pub)} Samples ──")
        run_bench(pub, "public")
        print(f"\n── Split heldout: {len(ho)} Samples ──")
        run_bench(ho, "heldout")
    else:
        run_bench(manifest, args.split if args.v3 else "legacy")


if __name__ == "__main__":
    main()
