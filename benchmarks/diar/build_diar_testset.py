#!/usr/bin/env python3
"""Change 136: Diarization-Testset-Builder (VoxPopuli-de, CC0, deterministisch).

Baut aus dem VoxPopuli-de-Test-Split (facebook/voxpopuli, CC0-1.0 — Public
Domain, frei veröffentlichbar) synthetische Mehrsprecher-Calls mit EXAKTER
Ground-Truth (wer spricht wann):

  - Basis: echte Parlaments-Reden (16 kHz), je Segment genau EIN Sprecher
    (`speaker_id`-GT aus dem Korpus).
  - Mehrsprecher-Mix: 2-4 Sprecher je Call, Segmente abwechselnd aneinander-
    gereiht mit kurzen Pausen (deterministisch, Seed 42) → GT exakt aus der
    Konstruktion (kein Label-Rauschen).
  - Lizenz: CC0 → Testset kann als GitHub-Release veröffentlicht werden
    (User-Entscheidung 26.08.: CALLHOME gated + CC-BY-NC-SA verworfen).

Struktur je Artefakt:
  audio/<call_id>.wav     (16 kHz mono)
  diar-manifest.json      (calls: [{id, speakers:[...], gt:[{start,end,speaker}]}])

Determinismus: feste Seeds, sortierte Iteration, feste Auswahl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import wave
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

SR = 16_000
SEED = 42

#: Segment-Auswahl: nur benannte Sprecher, mind. Dauer (Stille/Pausen raus)
MIN_SEG_S = 1.5
MAX_SEG_S = 20.0

#: Call-Komposition
CALLS_TOTAL = 20          # Calls im Testset
MIN_SPK = 2               # Sprecher je Call
MAX_SPK = 4
SEGS_PER_CALL = 8         # Segmente je Call (gleichmäßig über Sprecher)
PAUSE_RANGE = (0.3, 0.8)  # Pause zwischen Segmenten (s, deterministisch)


def load_metadata(parquet: Path) -> "tuple[dict, dict]":
    """Lädt Metadaten (ohne Audio) und liefert (segments, spk_segments).

    segments: audio_id -> (speaker_id, gender)
    spk_segments: speaker_id -> [audio_id, ...] (nur benannte Sprecher)
    """
    t = pq.read_table(str(parquet), columns=["audio_id", "speaker_id", "gender"])
    df = t.to_pandas()
    segments: dict = {}
    spk_segments: dict = {}
    for _, row in df.iterrows():
        sid = row["speaker_id"]
        if not sid or sid == "None":
            continue
        segments[row["audio_id"]] = (sid, row["gender"])
        spk_segments.setdefault(sid, []).append(row["audio_id"])
    return segments, spk_segments


def load_audio_bytes(parquet: Path, audio_ids: list[str]) -> dict[str, bytes]:
    """Lädt gezielt die audio-Bytes für die ausgewählten Segmente."""
    import pyarrow as pa
    import pyarrow.compute as pc

    t = pq.read_table(str(parquet), columns=["audio_id", "audio"])
    mask = pc.is_in(t.column("audio_id"), value_set=pa.array(audio_ids))
    t = t.filter(mask)
    out = {}
    for row in t.to_pylist():
        out[row["audio_id"]] = row["audio"]["bytes"]
    return out


def wav_to_16k_mono(wav_bytes: bytes, tmp: Path) -> np.ndarray:
    """Konvertiert eingebettete WAV-Bytes → float32-Array (16 kHz mono)."""
    src = tmp / "in.wav"
    src.write_bytes(wav_bytes)
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32767.0


def save_wav16k(path: Path, wav: np.ndarray) -> None:
    s16 = (np.clip(wav, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(s16.tobytes())


def build(out_dir: Path, parquet: Path, seed: int = SEED) -> None:
    """Erzeugt Testset + diar-manifest.json (deterministisch)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    tmp = out_dir / ".tmp"
    tmp.mkdir(exist_ok=True)

    segments, spk_segments = load_metadata(parquet)
    # Sprecher mit genug Segmenten (>= SEGS_PER_CALL/2, damit Mixe möglich)
    usable = {k: v for k, v in spk_segments.items() if len(v) >= 4}
    if len(usable) < MAX_SPK:
        raise SystemExit(
            f"Zu wenige Sprecher mit >=4 Segmenten ({len(usable)}) — Abbruch")
    print(f"Metadaten: {len(segments)} benannte Segmente, "
          f"{len(usable)} nutzbare Sprecher")

    rng = random.Random(seed)
    speakers = sorted(usable)  # deterministische Reihenfolge
    rng.shuffle(speakers)

    # Segment-Längen vorab bestimmen (nur ausgewählte, deterministisch)
    calls = []
    used_audio: set[str] = set()
    spk_pool_idx = 0
    for c in range(CALLS_TOTAL):
        n_spk = rng.randint(MIN_SPK, MAX_SPK)
        call_speakers = []
        for _ in range(n_spk):
            # rotierend durch den Sprecher-Pool (kein Sprecher in 2 Calls)
            sp = speakers[spk_pool_idx % len(speakers)]
            spk_pool_idx += 1
            call_speakers.append(sp)

        # Segmente je Sprecher auswählen (deterministisch)
        call_audio: list[tuple[str, str]] = []  # (audio_id, speaker)
        for si, sp in enumerate(call_speakers):
            cand = [a for a in usable[sp] if a not in used_audio]
            if not cand:
                continue
            n_seg = max(1, SEGS_PER_CALL // n_spk)
            pick = rng.sample(cand, min(n_seg, len(cand)))
            used_audio.update(pick)
            for a in pick:
                call_audio.append((a, sp))
        if len(call_audio) < 4:  # zu dünn → überspringen
            continue
        rng.shuffle(call_audio)  # Sprecher-Reihenfolge mischen
        calls.append({"id": f"call_{c:02d}", "speakers": call_speakers,
                      "segments": call_audio})

    # Audio laden + mixen
    all_audio_ids = [a for call in calls for a, _ in call["segments"]]
    print(f"Lade {len(all_audio_ids)} Audio-Segmente …")
    audio_bytes = load_audio_bytes(parquet, all_audio_ids)

    manifest_calls = []
    for call in calls:
        wav_parts: list[np.ndarray] = []
        gt: list[dict] = []
        t_cursor = 0.0
        for audio_id, sp in call["segments"]:
            wav = wav_to_16k_mono(audio_bytes[audio_id], tmp)
            if wav.size / SR < MIN_SEG_S or wav.size / SR > MAX_SEG_S:
                continue
            pause = rng.uniform(*PAUSE_RANGE)
            wav_parts.append(np.zeros(int(pause * SR), dtype=np.float32))
            start = t_cursor
            wav_parts.append(wav)
            t_cursor += pause + wav.size / SR
            gt.append({"start": round(start, 4), "end": round(t_cursor, 4),
                       "speaker": sp})
        if not gt:
            continue
        mix = np.concatenate(wav_parts)
        save_wav16k(audio_dir / f"{call['id']}.wav", mix)
        manifest_calls.append({
            "id": call["id"],
            "speakers": call["speakers"],
            "duration_s": round(mix.size / SR, 2),
            "gt": gt,
        })
        print(f"  {call['id']}: {len(gt)} Segmente, "
              f"{len(call['speakers'])} Sprecher, {mix.size / SR:.1f}s")

    manifest = {
        "version": 1,
        "source": "VoxPopuli-de Test-Split (facebook/voxpopuli, CC0-1.0)",
        "sample_rate": SR,
        "seed": seed,
        "created_at": "2026-08-26",
        "license": "CC0-1.0",
        "calls": manifest_calls,
    }
    (out_dir / "diar-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # SHA256 je WAV
    sha_lines = []
    for wav in sorted(audio_dir.glob("*.wav")):
        sha_lines.append(f"{hashlib.sha256(wav.read_bytes()).hexdigest()}  {wav.name}")
    (out_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    print(f"FERTIG: {len(manifest_calls)} Calls, "
          f"{sum(len(c['gt']) for c in manifest_calls)} Segmente, "
          f"{out_dir / 'diar-manifest.json'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path(__file__).parent / "assets" / "v1"))
    ap.add_argument("--parquet", default="/tmp/vox_de_test.parquet")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    build(Path(args.out), Path(args.parquet), seed=args.seed)


if __name__ == "__main__":
    main()
