#!/usr/bin/env python3
"""V3.1-Testset-Builder (Change 063/064): deterministisches VAD-Benchmark-Testset.

Erzeugt aus Piper-TTS-DE- und Common-Voice-DE-Basis-Samples + DEMAND/MUSAN/TEN-
Assets das V3.1-Testset mit public/held-out-Split und packt es als Artefakte:

  public:  assets/v3/           → vad-testset-v3.1-public.tar.gz (Release v4)
  heldout: assets/v3-heldout/   → NUR lokal, nie veröffentlicht

Struktur je Artefakt:
  testset.json   (id → {kind, variant, split, gt: [{start,end}], file, source})
  audio/<id>.wav (16 kHz mono)

Komposition:
  - Basis TTS: 10 DE-Synth-Samples × Stille-Insertion (lead2/trail2/both2/mid1)
  - Basis CV:  24 Common-Voice-DE-WAVs (akzent/child/clean) × Stille-Insertion
  - DEMAND-modifiziert: JEDES Basis-Sample × SNR 0/5/10 dB (Küche+Metro)
  - Babble: 2-Sprecher-Overlay · TEN-Testset (.scv-GT)
  - Noise-FP: weißes Rauschen + DEMAND 30 s · Musik-FP: MUSAN-Music 30 s

public/heldout-Split (nur CV + frische TTS-Varianten, Seed 42, 60/40):
  public  → GitHub-Release/ZIP/Repo/Container-Images
  heldout → ausschließlich lokal (assets/v3-heldout/, gitignored); der Runner
            lädt heldout nie vom Release und bricht ohne lokales Verzeichnis ab.

Determinismus: feste Seeds, feste Sample-Auswahl, sortierte Iteration.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import subprocess
import tarfile
import wave
from pathlib import Path

import numpy as np

SR = 16_000
HERE = Path(__file__).parent
ASSETS = HERE / "assets"
SPLIT_SEED = 42
PUBLIC_RATIO = 0.6


def load_wav16k(path: Path) -> np.ndarray:
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


def _regions(probs: np.ndarray, num_samples: int, window: int,
             threshold: float, min_speech_ms: int = 250,
             min_silence_ms: int = 400, speech_pad_ms: int = 120):
    """Region-Logik (silero-Semantik) — identisch mit vad_engines._regions."""
    min_speech = int(SR * min_speech_ms / 1000)
    min_silence = int(SR * min_silence_ms / 1000)
    pad = int(SR * speech_pad_ms / 1000)
    regions, current, silence = [], None, 0
    for i, p in enumerate(probs):
        start, end = i * window, i * window + window
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
            out.append((s / SR, e / SR))
    return out


def _energy_gt(wav: np.ndarray, window: int = 512, thresh_db: float = -40.0):
    probs = np.array([
        1.0 if np.sqrt((wav[i * window:(i + 1) * window] ** 2).mean()) > 10 ** (thresh_db / 20)
        else 0.0
        for i in range((wav.size - window) // window + 1)
    ], dtype=np.float32)
    return _regions(probs, wav.size, window=window, threshold=0.5)


def _shift_mid(seg, mid_at: float, mid_len: float):
    s, e = seg
    if e <= mid_at:
        return [(s, e)]
    if s >= mid_at:
        return [(s + mid_len, e + mid_len)]
    return [(s, mid_at), (mid_at + mid_len, e + mid_len)]


def _parse_scv(scv: Path):
    parts = scv.read_text().strip().split(",")[1:]
    regs, cur = [], None
    for i in range(0, len(parts), 3):
        start, end = float(parts[i]), float(parts[i + 1])
        speech = int(parts[i + 2])
        if speech:
            cur = [start, end] if cur is None else [cur[0], end]
        elif cur is not None:
            regs.append(tuple(cur))
            cur = None
    if cur is not None:
        regs.append(tuple(cur))
    return regs


def _split_assign(paths: list[Path], seed: int = SPLIT_SEED,
                  public_ratio: float = PUBLIC_RATIO) -> dict[Path, str]:
    """Deterministischer 60/40-Split: öffentlich vs held-out."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(paths))
    n_pub = int(round(len(paths) * public_ratio))
    assign = {}
    for i, p in enumerate(sorted(paths)):
        assign[p] = "public" if i in set(idx[:n_pub]) else "heldout"
    return assign


def add_synth_variants(samples: list[dict], audio: Path, wav: np.ndarray,
                       prefix: str, source: str, split: str,
                       variants=("lead2", "trail2", "both2"),
                       mid_cfg=(1.5, 1.0)) -> None:
    """Stille-Insertion-Varianten einer Basis-WAV + exakte GT."""
    gt = _energy_gt(wav)
    if not gt:
        return
    dur = wav.size / SR
    var_list = [("lead2", 2.0, None), ("trail2", 0.0, None), ("both2", 2.0, None)]
    if dur >= 4.0:
        var_list.append(("mid1", 0.0, mid_cfg))
    # falls Aufrufer eigene Varianten wünscht (heldout-TTS: lead3/trail3/both3)
    if variants != ("lead2", "trail2", "both2"):
        lead_map = {"lead2": 2.0, "trail2": 0.0, "both2": 2.0,
                    "lead3": 3.0, "trail3": 0.0, "both3": 3.0}
        var_list = [(v, lead_map[v], None) for v in variants]
        if dur >= 4.0:
            var_list.append(("mid1", 0.0, mid_cfg))
    for vname, lead, mid in var_list:
        if mid is not None:
            mid_at, mid_len = mid
            out_wav = np.concatenate([
                wav[: int(mid_at * SR)], np.zeros(int(mid_len * SR)),
                wav[int(mid_at * SR):], np.zeros(int(2.0 * SR)),
            ])
            g = []
            for s, e in gt:
                g.extend(_shift_mid((s, e), mid_at, mid_len))
        else:
            trail = 2.0 if vname in ("both2", "both3", "trail2", "trail3") else 0.0
            out_wav = np.concatenate([
                np.zeros(int(lead * SR)), wav, np.zeros(int(trail * SR)),
            ])
            g = [(s + lead, e + lead) for s, e in gt]
        sid = f"{prefix}_{vname}"
        save_wav16k(audio / f"{sid}.wav", out_wav)
        samples.append({"id": sid, "kind": "de_synth", "variant": vname,
                        "split": split, "source": source,
                        "gt": [{"start": round(a, 4), "end": round(b, 4)} for a, b in g]})


def add_snr_variants(samples: list[dict], audio: Path, wav: np.ndarray,
                     noises: list[Path], prefix: str, source: str, split: str,
                     snr_dbs=(0, 5, 10)) -> None:
    """DEMAND-modifizierte Basis-Samples: SNR-Stufen × 2 Quellen, GT exakt."""
    gt = _energy_gt(wav)
    if not gt:
        return
    speech_rms = float(np.sqrt((wav ** 2).mean())) or 1e-9
    for nidx, nf in enumerate(noises):
        noise = load_wav16k(Path(nf))
        noise_rms = float(np.sqrt((noise ** 2).mean())) or 1e-9
        for snr_db in snr_dbs:
            scale = (speech_rms * 10 ** (-snr_db / 20)) / noise_rms
            n = min(wav.size, noise.size)
            mix = wav[:n] + noise[:n] * scale
            mix = np.clip(mix, -1, 1).astype(np.float32)
            sid = f"{prefix}_snr{snr_db}_n{nidx}"
            save_wav16k(audio / f"{sid}.wav", mix)
            samples.append({"id": sid, "kind": "de_snr",
                            "variant": f"snr{snr_db}_n{nidx}", "split": split,
                            "source": source,
                            "gt": [{"start": round(a, 4), "end": round(b, 4)} for a, b in gt]})


def load_cv_metadata(sel_path: Path) -> dict[str, str]:
    """cv_accent_000.wav → Common-Voice-Quell-ID + Text (für Provenienz)."""
    sel_path = Path(sel_path)
    if not sel_path.exists():
        return {}
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    meta: dict[str, str] = {}
    for cat, entries in sel.get("categories", {}).items():
        for i, e in enumerate(entries):
            wav = f"cv_{cat}_{i:03d}.wav"
            src = e.get("source_path") or e.get("path") or ""
            meta[wav] = f"{src}|{e.get('text', '')}"
    return meta


def build(out_dir: Path, tts_dir: Path, ten_dir: Path,
          demand_dir: Path, music_dir: Path, cv_dir: Path,
          cv_selection: Path, split_mode: str = "all",
          max_tts: int = 12, snr_dbs=(0, 5, 10),
          version: int = 4) -> list[Path]:
    """Erzeugt Testset + testset.json je Split; packt tar.gz je Split.

    split_mode: "all" (public+heldout), "public", "heldout"
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tts_dir, ten_dir = Path(tts_dir), Path(ten_dir)
    demand_dir, music_dir = Path(demand_dir), Path(music_dir)
    cv_dir = Path(cv_dir)
    audio = out_dir / "audio"
    audio.mkdir(exist_ok=True)
    samples: list[dict] = []
    # Change 081: Sprecher-Provenienz — Dateinamen tragen seit Change 081
    # ein Sprecher-Suffix (tts_clean_000_thorsten.wav); ältere ohne Suffix
    # werden weiter erkannt (Glob matcht beide).
    tts = [Path(p) for p in sorted(glob.glob(str(tts_dir / "tts_clean_*.wav")))[:max_tts]]
    noises = [Path(p) for p in sorted(glob.glob(str(demand_dir / "*_sample.wav")))[:2]]
    rng = np.random.default_rng(42)
    cv_meta = load_cv_metadata(cv_selection)

    # ── Basis TTS (public) + DEMAND-modifiziert (nur public-Build) ─────
    if split_mode in ("all", "public"):
        for si, src in enumerate(tts):
            wav = load_wav16k(src)
            add_synth_variants(samples, audio, wav, f"de_{si:02d}", "piper-tts", "public")
            add_snr_variants(samples, audio, wav, noises, f"de_{si:02d}", "piper-tts", "public")

    # ── Basis CV (public/heldout je 60/40) + DEMAND-modifiziert ────────
    cv_wavs = [Path(p) for p in sorted(glob.glob(str(cv_dir / "cv_*.wav")))]
    assign = _split_assign(cv_wavs) if split_mode in ("all", "heldout", "public") else {}
    for src in cv_wavs:
        split = assign.get(src, "public")
        if split_mode == "public" and split != "public":
            continue
        if split_mode == "heldout" and split != "heldout":
            continue
        wav = load_wav16k(src)
        base = src.stem
        meta = cv_meta.get(f"{base}.wav", "")
        source = f"commonvoice:{base}" + (f" ({meta})" if meta else "")
        add_synth_variants(samples, audio, wav, base, source, split)
        add_snr_variants(samples, audio, wav, noises, base, source, split)

    # ── heldout: frische TTS-Varianten (lead3/trail3/both3, nie veröffentlicht)
    if split_mode in ("all", "heldout"):
        for si, src in enumerate(tts):
            wav = load_wav16k(src)
            add_synth_variants(samples, audio, wav, f"ho_de_{si:02d}",
                               "piper-tts", "heldout",
                               variants=("lead3", "trail3", "both3"))

    # ── Babble / TEN / Noise / Musik: immer public (FP-Referenzen) ──────
    if split_mode in ("all", "public"):
        if len(tts) >= 2:
            a = load_wav16k(tts[0])
            b = load_wav16k(tts[1])
            b = b * (float(np.sqrt((a ** 2).mean())) / (float(np.sqrt((b ** 2).mean())) or 1e-9))
            n = min(a.size, b.size + int(1.2 * SR))
            out = np.zeros(n, dtype=np.float32)
            out[: a.size] += a
            if n > int(1.2 * SR):
                out[int(1.2 * SR): int(1.2 * SR) + b.size] += b[: n - int(1.2 * SR)]
            out = np.clip(out, -1, 1).astype(np.float32)
            g = _energy_gt(a)
            save_wav16k(audio / "babble_2spk.wav", out)
            samples.append({"id": "babble_2spk", "kind": "babble", "variant": "2spk",
                            "split": "public", "source": "piper-tts",
                            "gt": [{"start": round(x, 4), "end": round(y, 4)} for x, y in g]})

        for scv in sorted(glob.glob(str(ten_dir / "testset-audio-*.scv")))[:10]:
            scv = Path(scv)
            wavf = ten_dir / f"{scv.stem}.wav"
            if not wavf.exists():
                continue
            gt = _parse_scv(scv)
            sid = f"ten_{scv.stem}"
            save_wav16k(audio / f"{sid}.wav", load_wav16k(wavf))
            samples.append({"id": sid, "kind": "ten", "variant": "ten",
                            "split": "public", "source": "ten-vad",
                            "gt": [{"start": round(a, 4), "end": round(b, 4)} for a, b in gt]})

        for i, dur in enumerate([10.0, 30.0]):
            noise = rng.standard_normal(int(dur * SR)).astype(np.float32) * 0.05
            sid = f"noise_white_{i}"
            save_wav16k(audio / f"{sid}.wav", noise)
            samples.append({"id": sid, "kind": "noise", "variant": "white",
                            "split": "public", "source": "synthetisch", "gt": []})
        for wavf in noises:
            w = load_wav16k(Path(wavf))[: 30 * SR]
            sid = f"noise_demand_{Path(wavf).stem}"
            save_wav16k(audio / f"{sid}.wav", w)
            samples.append({"id": sid, "kind": "noise", "variant": "demand",
                            "split": "public", "source": "demand", "gt": []})
        for wavf in sorted(glob.glob(str(music_dir / "*.wav")))[:3]:
            w = load_wav16k(Path(wavf))[: 30 * SR]
            sid = f"music_{Path(wavf).stem}"
            save_wav16k(audio / f"{sid}.wav", w)
            samples.append({"id": sid, "kind": "music", "variant": "musan",
                            "split": "public", "source": "musan", "gt": []})

    # ── Artefakt ────────────────────────────────────────────────────────
    manifest = {"version": version, "generated_at": "2026-08-26",
                "sample_rate": SR, "split": split_mode,
                "split_seed": SPLIT_SEED, "public_ratio": PUBLIC_RATIO,
                "samples": samples}
    (out_dir / "testset.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tag = f"v{version}" if version >= 4 else "v3.1"
    if split_mode != "all":
        tag = f"{tag}-{split_mode}"
    tar_path = out_dir / f"vad-testset-{tag}.tar.gz"
    import gzip
    # gzip-Header-mtime auf 0 → deterministische Artefakte (sonst ändert sich
    # der SHA256 bei jedem Build, obwohl alle Inhalte identisch sind)
    with gzip.GzipFile(filename=str(tar_path), mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for f in sorted(audio.glob("*.wav")):
                ti = tar.gettarinfo(str(f), arcname=f"audio/{f.name}")
                ti.mtime = 0; ti.uid = ti.gid = 0; ti.uname = ti.gname = ""
                with open(f, "rb") as fh:
                    tar.addfile(ti, fh)
            ti = tar.gettarinfo(str(out_dir / "testset.json"), arcname="testset.json")
            ti.mtime = 0; ti.uid = ti.gid = 0; ti.uname = ti.gname = ""
            with open(out_dir / "testset.json", "rb") as fh:
                tar.addfile(ti, fh)
    sha = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    print(f"V{version}-Testset ({split_mode}): {len(samples)} Samples, "
          f"{tar_path.name} ({tar_path.stat().st_size / 1e6:.1f} MB), SHA256 {sha[:16]}…")
    return [tar_path]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE / "assets" / "v3"))
    ap.add_argument("--heldout-dir", default=str(HERE / "assets" / "v3-heldout"))
    ap.add_argument("--split", choices=["all", "public", "heldout"], default="all")
    ap.add_argument("--tts-dir", default="/opt/data/polyschnack-benchmark/benchmark/data/tts")
    ap.add_argument("--cv-dir", default="/opt/data/polyschnack-benchmark/benchmark/data/common_voice")
    ap.add_argument("--cv-selection",
                    default="/opt/data/polyschnack-benchmark/benchmark/data/cv_selection.json")
    ap.add_argument("--ten-dir", default=str(ASSETS / "tenvad"))
    ap.add_argument("--demand-dir", default=str(ASSETS / "demand"))
    ap.add_argument("--music-dir", default=str(ASSETS / "musan" / "music"))
    ap.add_argument("--max-tts", type=int, default=12)
    args = ap.parse_args()

    if args.split == "all":
        build(Path(args.out), args.tts_dir, args.ten_dir,
              args.demand_dir, args.music_dir, args.cv_dir,
              args.cv_selection, split_mode="public", max_tts=args.max_tts)
        build(Path(args.heldout_dir), args.tts_dir, args.ten_dir,
              args.demand_dir, args.music_dir, args.cv_dir,
              args.cv_selection, split_mode="heldout", max_tts=args.max_tts)
    else:
        out = args.out if args.split == "public" else args.heldout_dir
        build(Path(out), args.tts_dir, args.ten_dir,
              args.demand_dir, args.music_dir, args.cv_dir,
              args.cv_selection, split_mode=args.split, max_tts=args.max_tts)


if __name__ == "__main__":
    main()
