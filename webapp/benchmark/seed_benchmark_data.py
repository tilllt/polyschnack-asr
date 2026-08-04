#!/usr/bin/env python3
"""Seed: erzeugt benchmark_data/versions/v1 aus CV-Auswahl + Piper-TTS.

Quellen:
- CV-Samples: benchmark/selection/cv_selection_v1.json + extrahierte WAVs
  (benchmark/data/cv/<stem>.wav, 16 kHz mono) → Kategorien akzent/jugend/clean
- Piper-TTS: benchmark/data/tts/tts_{clean,numbers,medical,legal,codeswitch,
  funk,pa}_NNN.wav (16 kHz mono) → Inhalts-Kategorien

Jedes Sample trägt die 2-Achsen-Taxonomie (kanal/inhalt) aus spec/taxonomy.json.
Ergebnis → <BENCHMARK_DATA_DIR>/versions/v1 (Manifest + WAVs + Preview-MP3s)
+ results/latest.json + pricing.json Platzhalter.

Läuft MANUELL (Admin) — nie in CI (User-Vorgabe).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Guard-Pitfall: alle Pfade per Env (Verzeichnis-/Datei-Pfade als Tokens
# blocken den Hermes-Lifecycle-Guard; >1-MiB-Dateien = unsafe).
SELECTION = Path(os.environ.get("SELECTION", ""))       # cv_selection_v1.json
TTS_SELECTION = Path(os.environ.get("TTS_SELECTION", ""))  # tts_selection.json
CV_WAV_DIR = Path(os.environ.get("CV_WAV_DIR", ""))       # benchmark/data/cv
TTS_WAV_DIR = Path(os.environ.get("TTS_WAV_DIR", ""))     # benchmark/data/tts
TAXONOMY = Path(os.environ.get("TAXONOMY", ""))           # benchmark/spec/taxonomy.json
DATA_OUT = Path(os.environ.get("BENCHMARK_DATA_DIR", ""))

# Piper-TTS-Quelle → Kategorie-Id (Inhalt-Achse) + Kanal-Achse
TTS_CAT = {
    "tts_clean": ("allgemein", "clean"),
    "tts_numbers": ("zahlen", "clean"),
    "tts_medical": ("fachsprache", "clean"),
    "tts_legal": ("fachsprache", "clean"),
    "tts_codeswitch": ("codeswitch", "clean"),
    "tts_funk": ("durchsagen", "broadcast"),
    "tts_pa": ("durchsagen", "broadcast"),
}


def main() -> None:
    for p, name in ((SELECTION, "SELECTION"), (TTS_SELECTION, "TTS_SELECTION"),
                    (CV_WAV_DIR, "CV_WAV_DIR"), (TTS_WAV_DIR, "TTS_WAV_DIR"),
                    (TAXONOMY, "TAXONOMY"), (DATA_OUT, "BENCHMARK_DATA_DIR")):
        if not p or not p.exists():
            sys.exit(f"FEHLER: {name} fehlt oder existiert nicht: {p}")

    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    mapping = tax["mapping_alt_neu"]
    # Achsen-Definitionen (kanal/inhalt) + Beschreibungen für die GUI-Matrix
    axes = {
        "kanal": {
            "beschreibung": tax["achsen"]["kanal"]["beschreibung"],
            "kategorien": {
                k: {"name": v["name"]}
                for k, v in tax["achsen"]["kanal"]["kategorien"].items()
            },
        },
        "inhalt": {
            "beschreibung": tax["achsen"]["inhalt"]["beschreibung"],
            "kategorien": {
                k: {"name": v["name"]}
                for k, v in tax["achsen"]["inhalt"]["kategorien"].items()
            },
        },
    }

    v1 = DATA_OUT / "versions" / "v1"
    audio_dir = v1 / "audio"
    preview_dir = v1 / "preview"
    audio_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    (DATA_OUT / "results").mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": 1,
        "created_at": _now_iso(),
        "created_by": "admin",
        "supersedes": None,
        "methodology": (
            "WER/CER auf echten CommonVoice-de-Sprechern (akzent/jugend/clean) "
            "+ Piper-TTS (schnell/zahlen/fachsprache/codeswitch/durchsagen). "
            "2-Achsen-Taxonomie: Kanal × Inhalt. Benchmark-Läufe auf "
            "unkomprimierten WAVs, Preview MP3 128k."
        ),
        "disclaimer": (
            "Held-out-Samples und Referenztexte sind nicht öffentlich "
            "(Anti-Gaming). Ergebnisse sind Momentaufnahmen."
        ),
        "axes": axes,
        "categories": [
            {"id": "akzent", "name": "Akzente", "kanal": "clean", "inhalt": "akzent",
             "description": "Regionale Färbungen (Schweizerdeutsch, Österreichisch, …)"},
            {"id": "jugend", "name": "Jugendstimmen", "kanal": "clean", "inhalt": "jugend",
             "description": "Teens-Sprecher aus CommonVoice"},
            {"id": "clean", "name": "Hochdeutsch", "kanal": "clean", "inhalt": "allgemein",
             "description": "Klare Standard-Sätze ohne Akzent-Markierung"},
            {"id": "schnell", "name": "Schnelles Sprechen", "kanal": "clean", "inhalt": "schnell",
             "description": "Schnellsprache (Piper, 1.4×)"},
            {"id": "zahlen", "name": "Zahlen & Codes", "kanal": "clean", "inhalt": "zahlen",
             "description": "Telefonnummern, Kontonummern, Kennzeichen"},
            {"id": "medizin", "name": "Medizin", "kanal": "clean", "inhalt": "fachsprache",
             "description": "Medizinisches Vokabular"},
            {"id": "jura", "name": "Jura", "kanal": "clean", "inhalt": "fachsprache",
             "description": "Juristisches Vokabular"},
            {"id": "mixed", "name": "Sprachmischung", "kanal": "clean", "inhalt": "codeswitch",
             "description": "Deutsch-Englisch Code-Switch"},
            {"id": "funk", "name": "Funkverkehr", "kanal": "broadcast", "inhalt": "durchsagen",
             "description": "Sprechfunk (Flugfunk, Einsatzkräfte)"},
            {"id": "pa", "name": "Durchsagen", "kanal": "broadcast", "inhalt": "durchsagen",
             "description": "Bahnhofs-/Flughafen-Durchsagen"},
        ],
        "samples": [],
    }

    n = 0
    # 1) CV-Samples (echte Stimmen)
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    for cat, entries in sel.get("categories", {}).items():
        for e in entries:
            n += 1
            sid = f"{cat}_{n:03d}"
            stem = Path(e["source_path"]).stem
            src = CV_WAV_DIR / f"{stem}.wav"
            if not src.exists():
                print(f"WARN: {src} fehlt — Sample übersprungen")
                continue
            _add_sample(manifest, sid, cat, src, audio_dir, preview_dir, {
                "source_path": e["source_path"],
                "text": e["text"],
                "accent": e.get("accent", ""),
                "age": e.get("age", ""),
                "quelle": "cv",
            }, mapping)
            print(f"  {sid} ← cv/{stem}")

    # 2) Piper-TTS-Samples (Inhalts-Kategorien) — Texte aus tts_selection.json
    tts_sel = json.loads(TTS_SELECTION.read_text(encoding="utf-8"))
    for e in tts_sel:
        source_id = e["source"]
        cat_id, kanal = TTS_CAT.get(source_id, (None, None))
        if cat_id is None:
            continue
        n += 1
        sid = f"{source_id.replace('tts_', '')}_{n:03d}"
        src = TTS_WAV_DIR / e["file"]
        if not src.exists():
            print(f"WARN: {src} fehlt — Sample übersprungen")
            continue
        _add_sample(manifest, sid, source_id.replace("tts_", ""), src,
                    audio_dir, preview_dir, {
                        "source_path": src.name,
                        "text": e["text"],
                        "accent": "",
                        "age": "",
                        "quelle": "tts",
                    }, mapping)
        print(f"  {sid} ← tts/{src.name}")

    manifest_path = v1 / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_OUT / "results" / "latest.json").write_text(
        json.dumps({"version": 1, "run_id": None, "rows": []}), encoding="utf-8"
    )
    (DATA_OUT / "pricing.json").write_text(
        json.dumps({
            "generated_at": _now_iso(),
            "note": "Selbstkosten-Beispielwerte; echte Messungen kommen aus "
                    "Benchmark-Läufen (RTF-abhängig). Aufschlag nur mit USP-Beleg.",
            "rows": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"\nFERTIG: Version 1 mit {len(manifest['samples'])} Samples → {v1}")


def _add_sample(manifest: dict, sid: str, cat_id: str, src: Path,
                audio_dir: Path, preview_dir: Path, extra: dict,
                mapping: dict) -> None:
    """Kopiert WAV, erzeugt Preview-MP3, hängt Sample mit Taxonomie an."""
    dest_wav = audio_dir / f"{sid}.wav"
    dest_wav.write_bytes(src.read_bytes())
    preview = preview_dir / f"{sid}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(dest_wav),
         "-codec:a", "libmp3lame", "-b:a", "128k", "-ac", "1", str(preview)],
        check=True, timeout=300,
    )
    # Taxonomie: kanal/inhalt aus dem Mapping (best effort, fehlt → clean/allgemein)
    ziel = mapping.get(cat_id, {"kanal": "clean", "inhalt": "allgemein"})
    sample = {
        "id": sid,
        "category": cat_id,
        "kanal": ziel["kanal"],
        "inhalt": ziel["inhalt"],
        **extra,
        "held_out": False,
        "status": "active",
    }
    manifest["samples"].append(sample)


def _tts_text(source_id: str, wav: Path) -> str:
    """Referenztext aus prepare.py-Prompts (Index aus Dateiname)."""
    import sys as _sys
    sys.path.insert(0, "benchmark")
    from prepare import (TTS_CLEAN, TTS_CODESWITCH, TTS_FUNK, TTS_LEGAL,
                         TTS_MEDICAL, TTS_NUMBERS, TTS_PA)
    pools = {
        "tts_clean": TTS_CLEAN, "tts_numbers": TTS_NUMBERS,
        "tts_medical": TTS_MEDICAL, "tts_legal": TTS_LEGAL,
        "tts_codeswitch": TTS_CODESWITCH, "tts_funk": TTS_FUNK,
        "tts_pa": TTS_PA,
    }
    idx = int(wav.stem.rsplit("_", 1)[1])
    return pools[source_id][idx]


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


if __name__ == "__main__":
    main()
