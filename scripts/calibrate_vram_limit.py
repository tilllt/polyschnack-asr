#!/usr/bin/env python3
"""VRAM-Kurve eines laufenden ASR-Jobs messen — Kalibrierung für
`long_audio.auto_vram` (backends.yaml).

Warum: Die dynamische Grenze rechnet `(freier VRAM - Safety) / vram_per_minute`.
`vram_per_minute_gb` ist modellabhängig (CrispASR lädt lange Dateien am Stück;
der VRAM wächst mit der Länge). Dieser Wert wird gemessen, nicht geraten.

So messen: Auf der KI-Box eine lange Datei (z. B. 60–120 min) über die Webapp
transkribieren und WÄHREND des Jobs dieses Skript laufen lassen:

    python3 calibrate_vram_limit.py --seconds 900 --interval 5

Ausgabe: CSV (t, used_mb, free_mb) + Peak. Daraus:

    vram_per_minute_gb ≈ (peak_used_gb - model_base_gb) / datei_minuten

wobei model_base_gb der Leerlauf-VRAM des Modells ist (nvidia-smi ohne Job,
bzw. `requires.vram_gb` als grobe Näherung). Ergebnis in backends.yaml eintragen.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time


def _nvidia_lines() -> list[str] | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=int, default=600, help="Messdauer in Sekunden (Jobdauer)")
    ap.add_argument("--interval", type=int, default=5, help="Sampling-Intervall in Sekunden")
    args = ap.parse_args()

    if not _nvidia_lines():
        print("FEHLER: nvidia-smi nicht erreichbar — Skript auf dem GPU-Host ausführen.", file=sys.stderr)
        return 1

    print("t_s,used_mb,free_mb")
    peak_used = 0
    start = time.monotonic()
    while True:
        elapsed = int(time.monotonic() - start)
        lines = _nvidia_lines()
        if lines:
            used_mb, free_mb = (int(x) for x in lines[0].split(","))
            peak_used = max(peak_used, used_mb)
            print(f"{elapsed},{used_mb},{free_mb}", flush=True)
        if elapsed >= args.seconds:
            break
        time.sleep(max(1, args.interval))

    print(f"\nPEAK used: {peak_used / 1024:.2f} GB", flush=True)
    print("Tipp: vram_per_minute_gb ≈ (peak_used_gb - model_base_gb) / datei_minuten", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
