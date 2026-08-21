#!/usr/bin/env python3
"""Einheitliches VAD-Container-CLI (Change 062): Audio → regions.json.

Jeder VAD-Container bündelt genau eine Engine aus vad_engines.py (per
VAD_ENGINE oder --engine). Interface für Selfservice + vast-Benchmark:

    vad_run.py --audio in.wav --out regions.json
    → {"engine": "silero_onnx", "license": "MIT — produktiv nutzbar",
       "rtf": 0.02, "regions": [{"start": 0.1, "end": 2.3}, ...]}

Audio-Formate: alles, was ffmpeg liest (wav/mp3/m4a/ogg/...).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from vad_engines import ENGINES, LICENSES, SR

def load_wav16k(path: Path) -> np.ndarray:
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32767.0

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, help="Eingabe-Audiodatei")
    ap.add_argument("--out", default="regions.json", help="Ausgabe-Pfad")
    ap.add_argument("--engine", default=os.environ.get("VAD_ENGINE", ""),
                    help="Engine-Name (Default: VAD_ENGINE env)")
    args = ap.parse_args()

    engine = args.engine
    if engine not in ENGINES:
        sys.stderr.write(f"Unbekannte Engine '{engine}'. Verfügbar: {', '.join(ENGINES)}\n")
        return 2
    wav = load_wav16k(Path(args.audio))
    regions, elapsed = ENGINES[engine](wav)
    dur = wav.size / SR
    payload = {
        "engine": engine,
        "license": LICENSES.get(engine, "?"),
        "rtf": round(elapsed / dur, 6) if dur > 0 else 0.0,
        "infer_s": round(elapsed, 4),
        "audio_s": round(dur, 3),
        "regions": [{"start": round(s, 4), "end": round(e, 4)} for s, e in regions],
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload))
    return 0

if __name__ == "__main__":
    sys.exit(main())
