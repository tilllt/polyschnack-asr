#!/usr/bin/env python3
"""Aligner-Benchmark-Auswertung: qwen3 vs TADA vs wav2vec2.

Vergleicht je Paar die Wort-Timestamps (Kreuz-Δ) + Metriken.
"""
import json, sys, os

def load(p):
    d = json.load(open(p))
    if isinstance(d, dict):
        d = d.get("words") or d.get("segments") or []
    return d

def analyze(run_dir, label, ref_words):
    files = {
        "qwen3": os.path.join(run_dir, "qwen.json"),
        "tada": os.path.join(run_dir, "tada.json"),
        "wav2vec2": os.path.join(run_dir, "wav2vec.json"),
    }
    time_files = {"qwen3": "qwen", "tada": "tada", "wav2vec2": "wav2vec"}
    times = {}
    for name, p in files.items():
        tf = os.path.join(run_dir, time_files[name] + ".time")
        if os.path.exists(tf):
            raw = open(tf).read().strip().replace(" ms", "")
            times[name] = float(raw) / 1000.0
        else:
            times[name] = None
    data = {n: load(p) for n, p in files.items()}

    print(f"\n{'='*70}\n{label}\n{'='*70}")
    print(f"Referenzwörter: {ref_words}")

    # Normalisiere Wortfolge (klein, ohne Satzzeichen) für das Matching
    import re
    def norm(w):
        return re.sub(r"[^a-zäöüß0-9]", "", w.lower())

    for name, words in data.items():
        n = len(words)
        timed = [x for x in words if abs((x.get("end") or 0) - (x.get("start") or 0)) >= 0.001]
        zero = n - len(timed)
        last = timed[-1].get("end", 0) if timed else 0
        # Wortfolge-Abdeckung: wie viele Referenzwörter erscheinen in Reihenfolge
        seq = [norm(x.get("word", "")) for x in words if norm(x.get("word", ""))]
        ref_norm = [norm(w) for w in ref_words if norm(w)]
        i = j = matched = 0
        while i < len(seq) and j < len(ref_norm):
            if seq[i] == ref_norm[j]:
                matched += 1
                i += 1
                j += 1
            else:
                j += 1
        cov = matched / len(ref_norm) * 100 if ref_norm else 0
        abdeckung = len(timed) / len(ref_norm) * 100 if ref_norm else 0
        print(f"\n  {name:9s} Wörter={n:3d}  davon mit Zeit={len(timed):3d}  "
              f"0-Dauer={zero:2d}  Zeitabdeckung={abdeckung:3.0f}%  "
              f"Ende={last:6.2f}s  "
              f"Laufzeit={times[name] if times[name] is not None else float('nan'):6.1f}s  "
              f"Wortfolge={cov:.0f}%")

    # Paarweiser Kreuzvergleich: nur Wörter, die in beiden (positional) existieren
    pairs = [("qwen3", "tada"), ("qwen3", "wav2vec2"), ("tada", "wav2vec2")]
    for a, b in pairs:
        wa, wb = data[a], data[b]
        n = min(len(wa), len(wb))
        ds, de = [], []
        for i in range(n):
            x, y = wa[i], wb[i]
            if abs((x.get("end") or 0) - (x.get("start") or 0)) < 0.001:
                continue
            if abs((y.get("end") or 0) - (y.get("start") or 0)) < 0.001:
                continue
            ds.append(abs((x.get("start") or 0) - (y.get("start") or 0)))
            de.append(abs((x.get("end") or 0) - (y.get("end") or 0)))
        if ds:
            print(f"  Δ {a:8s} vs {b:8s}: start {sum(ds)/len(ds)*1000:6.1f} ms  "
                  f"end {sum(de)/len(de)*1000:6.1f} ms  (n={len(ds)})")
        else:
            print(f"  Δ {a} vs {b}: keine vergleichbaren Wörter")

if __name__ == "__main__":
    base = "/opt/data/pk-asr/benchmark/aligner"
    analyze(os.path.join(base, "run_poc"),
            "TEST 1: TTS-Aufnahme 19,5 s (exakter Referenztext, Ground-Truth-Wortfolge)",
            open(os.path.join(base, "ref_poc.txt")).read().split())
    analyze(os.path.join(base, "run_team"),
            "TEST 2: Teamtreffen-Clip 90 s (Real-World, ASR-Referenztext)",
            open(os.path.join(base, "ref_teamtreffen90.txt")).read().split())
