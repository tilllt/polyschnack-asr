#!/usr/bin/env python3
"""Change 136: Diar-Container-CLI (Audio → Segmente).

Analog vad_run.py: einheitliches Interface für Selfservice + Benchmark:

    diar_run.py --audio in.wav --out segments.json --method foxnose
    → {"method": "foxnose", "license": "…", "rtf": 0.5,
       "segments": [{"start": 0.0, "end": 5.1, "speaker": "SPEAKER_00"}, ...]}

Ruft den CrispASR-diar-Service (POST /v1/audio/transcriptions mit
response_format=diarized_json) — identisch zur Webapp-Schnittstelle
(webapp/app/diarize.py). DIAR_URL env oder --url; --method foxnose
(Default) | pyannote | vad-turns.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

METHODS = ("foxnose", "pyannote", "vad-turns", "energy", "xcorr")
DEFAULT_URL = os.environ.get("DIAR_URL", "http://localhost:5098")


def diarize(audio_path: str, method: str, url: str) -> tuple:
    """POST an den diar-Service → (segments, infer_s)."""
    if method not in METHODS:
        raise ValueError(f"unbekannte Methode {method!r} — erlaubt: {', '.join(METHODS)}")
    endpoint = f"{url.rstrip('/')}/v1/audio/transcriptions"
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    data = {
        "response_format": "diarized_json",
        "diarize": "true",
        "diarize_method": method,
        # Change 126: Embedder erzwingen, sonst bleiben Labels chunk-lokal
        "diarize_embedder": "auto",
        "chunk_seconds": "60",
    }
    wav_name = Path(audio_path).stem + ".wav"
    t0 = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(1800, connect=30)) as client:
        resp = client.post(endpoint, files={"file": (wav_name, audio_bytes, "audio/wav")}, data=data)
    infer_s = time.perf_counter() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"diar-Service HTTP {resp.status_code}: {resp.text[:300]}")
    segments = []
    for seg in resp.json().get("segments") or []:
        segments.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "speaker": str(seg.get("speaker", "SPEAKER_00")),
        })
    return segments, infer_s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, help="Eingabe-Audiodatei")
    ap.add_argument("--out", default="segments.json", help="Ausgabe-Pfad")
    ap.add_argument("--method", default=os.environ.get("DIARIZE_METHOD", "foxnose"),
                    help="Methode (Default: DIARIZE_METHOD env / foxnose)")
    ap.add_argument("--url", default=DEFAULT_URL, help="diar-Service-URL")
    args = ap.parse_args()

    try:
        segments, infer_s = diarize(args.audio, args.method, args.url)
    except (RuntimeError, httpx.HTTPError) as e:
        sys.stderr.write(f"FEHLER: {e}\n")
        return 2

    from diar_metrics import total_speech
    dur = total_speech([(s["start"], s["end"], s["speaker"]) for s in segments]) or 0.0
    payload = {
        "method": args.method,
        "rtf": round(infer_s / dur, 4) if dur > 0 else 0.0,
        "infer_s": round(infer_s, 3),
        "segments": segments,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
