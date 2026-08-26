#!/usr/bin/env python3
"""V3.1/V4-Release-ZIP-Assembly (Change 064, 081): public-Teil + Provenienz.

Packt für externe User ein ZIP mit:
  audio/<id>.wav        (nur public-Samples)
  testset.json          (GT + split + source je Sample)
  PROVENANCE.md         (Quellen, Lizenzen, Seeds, Erzeugung, SHA256)
  results_v3_public.json (falls vorhanden — Benchmark-Ergebnisse)

Guard: KEIN heldout-Sample darf ins ZIP (Leakage-Schutz, Change 064).
Ausgabe: vad-benchmark-v4-public.zip + SHA256 (stdout + .sha256-Datei).

Change 081: Version 4 — TTS-Quellen Thorsten/VibeVoice-f (Ramona entfernt);
Dateiname/Header versioniert via --version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
OUT = HERE / "out"

# Quellen-Kategorien → Provenienz (für PROVENANCE.md)
LICENSES = {
    "piper-tts": "Piper TTS (rhasspy/piper), MIT; deutsche Stimme Thorsten/VibeVoice-f (CC0)",
    "commonvoice": "Mozilla Common Voice DE (CC0-1.0); Auswahl via cv_selection.json (Seed 42, 24 Samples)",
    "demand": "DEMAND (Zenodo 1227121, CC-BY-4.0) — Küche/Metro, 16 kHz",
    "musan": "MUSAN (Mozilla, CC-BY-4.0) — Musik-Sektion, 16 kHz",
    "ten-vad": "TEN-VAD-Testset (Agora, Apache-2.0 + Agora-Klauseln) — NUR Referenz, nicht produktiv",
    "synthetisch": "Weißes Rauschen (numpy, Seed 42)",
    "n/a": "—",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_category(source: str) -> str:
    if not source:
        return "n/a"
    for key in ("commonvoice", "piper-tts", "demand", "musan", "ten-vad", "synthetisch"):
        if key in source:
            return key
    return "n/a"


def build_provenance(testset: dict, samples: list[dict], zip_path: Path,
                     results_path: Path | None) -> str:
    cats: dict[str, list[str]] = {}
    for s in samples:
        cats.setdefault(source_category(s.get("source", "")), []).append(s["id"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ver = testset.get("version", 4)
    lines = [
        f"# PROVENANCE — PolySchnack VAD-Benchmark-Testset V{ver} (public)",
        "",
        f"Erzeugt: {now} · Skript: `benchmarks/vad/build_testset_v3.py` "
        f"(Change 063/064/081, deterministisch, feste Seeds) · Sample-Rate: {testset['sample_rate']} Hz",
        "",
        "## Split-Politik",
        "",
        "Dieses ZIP enthält NUR den **public**-Split. Ein **held-out**-Split "
        "(andere Stille-Insertionen + frische TTS-Varianten, 126 Samples) wird "
        "bewusst NICHT veröffentlicht: Sobald ein Testset öffentlich ist, kann "
        "es in Trainingsdaten einfließen (Leakage) und die Benchmark-Zahlen "
        "sind nicht mehr ehrlich. Held-out-Ergebnisse werden intern geführt; "
        "das Repo/Mirror (GitHub, Harbor) enthält niemals held-out-Audio.",
        "",
        "## Komposition",
        "",
        f"- **{len(samples)} Samples gesamt** (public): "
        f"{sum(1 for s in samples if s['kind']=='de_synth')} DE-Synth "
        f"(Stille-Insertion, exakte GT), {sum(1 for s in samples if s['kind']=='de_snr')} "
        f"SNR-Mix (DEMAND 0/5/10 dB), {sum(1 for s in samples if s['kind']=='babble')} Babble, "
        f"{sum(1 for s in samples if s['kind']=='ten')} TEN, "
        f"{sum(1 for s in samples if s['kind']=='noise')} Noise, "
        f"{sum(1 for s in samples if s['kind']=='music')} Musik",
        "",
        "## Quellen & Lizenzen",
        "",
        "| Kategorie | Quelle | Lizenz | Samples |",
        "|---|---|---|---|",
    ]
    for cat in sorted(cats):
        ids = cats[cat]
        lines.append(f"| {cat} | {LICENSES.get(cat, '?')} | {len(ids)} |")
    lines += [
        "",
        "### Quellen-Details",
        "",
        "- **Piper-TTS**: `tts_clean_*.wav` aus dem PolySchnack-ASR-Testset "
        "(piper, deutsche Stimmen Thorsten/VibeVoice-f).",
        "- **Common Voice DE**: Mozilla Common Voice (CC0). Auswahl per "
        "`cv_selection.json` (Seed 42): 8 akzent / 8 child / 8 clean, je "
        "einzeln zuordenbar via `source`-Feld im testset.json "
        "(z. B. `commonvoice:cv_accent_000 (common_voice_de_40129100.mp3|Text)`).",
        "- **DEMAND**: Zenodo 1227121, `DKITCHEN_16k` + `TMETRO_16k` "
        "(je 300 s), CC-BY-4.0 — lizenz-kompatibel für kommerzielle Nutzung.",
        "- **MUSAN**: `corypaik/musan` (HF-Mirror des Mozilla-Korpus, CC-BY-4.0), "
        "Musik-Sektion, 16-kHz-mono.",
        "- **TEN-VAD-Testset**: Agora TEN-VAD `.scv`-GT — Apache-2.0 MIT "
        "Nutzungsklausel (kein konkurrierender Einsatz) → nur Referenz.",
        "",
        "## Determinismus & Integrität",
        "",
        f"- **Erzeugung**: `build_testset_v3.py` (feste Seeds: Insertion-Seeds, "
        f"Split-Seed {testset.get('split_seed', 42)}, Public-Ratio "
        f"{testset.get('public_ratio', 0.6)}); gzip-mtime=0 → identische "
        "Artefakte bei Wiederholung.",
        f"- **ZIP-SHA256**: `{sha256(zip_path)}`",
        "- **Audio-SHA256**: je Datei in `SHA256SUMS` (im ZIP enthalten).",
        "",
        "## Benchmark-Ergebnisse",
        "",
    ]
    if results_path and results_path.exists():
        res = json.loads(results_path.read_text(encoding="utf-8"))
        lines += ["`results_v3_public.json` (im ZIP enthalten) — Spalten siehe "
                  "README (benchmarks/vad). Kurzfassung:"]
        agg = res.get("agg", {})

        def _mean(v):
            if isinstance(v, list) and v:
                return sum(v) / len(v)
            return v

        for eng, a in sorted(agg.items()):
            f1 = _mean(a.get("f1"))
            f1s = f"{f1:.3f}" if isinstance(f1, float) else "—"
            rtf = _mean(a.get("rtf"))
            rtf_s = f"{rtf:.4f}" if isinstance(rtf, float) else "—"
            lines.append(f"- **{eng}**: n={a.get('n', '?')}, F1={f1s}, "
                         f"FP-Speech={_mean(a.get('fp_time', '?')):.1f} s, "
                         f"RTF={rtf_s}")
    else:
        lines.append("Noch keine Ergebnisse — `run_benchmark.py --v3 --split public` "
                     "ausführen und `out/results_v3_public.json` beilegen.")
    lines.append("")
    return "\n".join(lines)


def assemble(v3_dir: Path, out_dir: Path, zip_path: Path,
             results_path: Path | None) -> Path:
    testset = json.loads((v3_dir / "testset.json").read_text(encoding="utf-8"))
    samples = testset["samples"]
    heldout = [s for s in samples if s.get("split") != "public"]
    if heldout:
        raise SystemExit(f"Leakage-Guard: {len(heldout)} heldout-Samples im "
                         f"public-Testset gefunden — ZIP abgebrochen.")
    audio_dir = v3_dir / "audio"
    sha_lines: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for s in sorted(samples, key=lambda x: x["id"]):
            wav = audio_dir / f"{s['id']}.wav"
            if not wav.exists():
                raise SystemExit(f"WAV fehlt: {wav}")
            z.write(wav, f"audio/{s['id']}.wav")
            sha_lines.append(f"{sha256(wav)}  audio/{s['id']}.wav")
        z.write(v3_dir / "testset.json", "testset.json")
        z.writestr("SHA256SUMS", "\n".join(sha_lines) + "\n")
        prov = build_provenance(testset, samples, zip_path, results_path)
        z.writestr("PROVENANCE.md", prov)
        if results_path and results_path.exists():
            z.write(results_path, "results_v3_public.json")
    total = sha256(zip_path)
    (zip_path.parent / f"{zip_path.name}.sha256").write_text(f"{total}  {zip_path.name}\n")
    print(f"ZIP: {zip_path.name} ({zip_path.stat().st_size / 1e6:.1f} MB, "
          f"{len(samples)} public-Samples), SHA256 {total[:16]}…")
    return zip_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v3-dir", default=str(ASSETS / "v4"))
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--version", default="4",
                    help="Versions-Label für ZIP-Dateiname + PROVENANCE (4 oder 3.1)")
    ap.add_argument("--zip", default=None,
                    help="Ziel-ZIP (Default: vad-benchmark-v{version}-public.zip)")
    ap.add_argument("--results", default=str(OUT / "results_v3_public.json"))
    args = ap.parse_args()
    version = args.version
    zip_path = Path(args.zip) if args.zip else HERE / f"vad-benchmark-v{version}-public.zip"
    results_path = Path(args.results)
    assemble(Path(args.v3_dir), Path(args.out), zip_path,
             results_path if results_path.exists() else None)


if __name__ == "__main__":
    main()
