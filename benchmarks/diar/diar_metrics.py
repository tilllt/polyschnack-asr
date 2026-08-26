#!/usr/bin/env python3
"""Change 136: Diarization-Metriken (DER, Jaccard, Sprecherzahl) — pure Python.

DER (Diarization Error Rate) = (Missed + False Alarm + Speaker Confusion) /
Total-Speech-Time — Standard-Metrik der Diarization-Literatur (NIST RT).

Berechnung:
  1. GT/Hyp zu (start, end, speaker)-Intervallen kollabieren.
  2. Optimale Bijektion Hyp-Sprecher → GT-Sprecher (brute force über
     Permutationen — Testset hat ≤4 Sprecher/Call) mit maximaler
     korrekt-zuordenbarer Zeit.
  3. Fehlerzeit = Gesamtzeit − korrekt zugeordnete Zeit → DER.

Zusätzlich:
  - jaccard_per_segment: mittlere segmentweise Jaccard-Ähnlichkeit
  - speaker_count_error: |n_gt − n_hyp| je Call
  - Der GT ist bei uns synthetisch EXAKT (aus der Mix-Konstruktion),
    Label-Rauschen gibt es nicht.
"""
from __future__ import annotations

import itertools
from typing import List, Sequence, Tuple

Segment = Tuple[float, float, str]  # (start, end, speaker)


def collapse(segments: Sequence[Segment]) -> List[Segment]:
    """Verschmilzt benachbarte Segmente desselben Sprechers (kein Overlap hier)."""
    out: List[Segment] = []
    for s, e, spk in sorted(segments, key=lambda x: (x[0], x[1])):
        if out and out[-1][2] == spk and abs(out[-1][1] - s) < 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], e), spk)
        else:
            out.append((s, e, spk))
    return out


def total_speech(segments: Sequence[Segment]) -> float:
    return sum(max(0.0, e - s) for s, e, _ in segments)


def _overlap(a: Segment, b: Segment) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _correct_time(gt: Sequence[Segment], hyp: Sequence[Segment],
                  mapping: dict) -> float:
    """Korrekt zugeordnete Sprechzeit unter einer Sprecher-Zuordnung."""
    total = 0.0
    for gs, ge, gspk in gt:
        hspk = mapping.get(gspk)
        if hspk is None:
            continue
        # Summe des Overlaps aller Hyp-Segmente dieses Sprechers mit dem GT-Segment
        total += sum(_overlap((gs, ge, gspk), h) for h in hyp if h[2] == hspk)
    return min(total, total_speech(gt))  # nie mehr als GT-Sprechzeit


def der(gt: Sequence[Segment], hyp: Sequence[Segment]) -> Tuple[float, dict]:
    """DER + Detail (missed, false_alarm, confusion, correct, mapping)."""
    gt = collapse(gt)
    hyp = collapse(hyp)
    gt_spk = sorted({s for _, _, s in gt})
    hyp_spk = sorted({s for _, _, s in hyp})
    total = total_speech(gt)
    if total <= 0:
        return 1.0, {"reason": "keine GT-Sprechzeit"}

    best_correct, best_map = -1.0, {}
    # Injektive (partielle) Zuordnung: jeder Hyp-Sprecher höchstens einem
    # GT-Sprecher. Bei weniger Hyp- als GT-Sprechern bleiben GT-Sprecher
    # ungemappt (→ Missed); bei mehr Hyp-Sprechern bleiben welche übrig
    # (→ Confusion). Brute force über alle Teilmengen + Permutationen —
    # Testset-Calls haben ≤4 Sprecher, das ist trivial.
    for k in range(min(len(gt_spk), len(hyp_spk)) + 1):
        for subset in itertools.combinations(gt_spk, k):
            for perm in itertools.permutations(hyp_spk, k):
                mapping = dict(zip(subset, perm))
                c = _correct_time(gt, hyp, mapping)
                if c > best_correct:
                    best_correct, best_map = c, mapping

    best_correct = max(0.0, best_correct)
    der_val = 1.0 - best_correct / total
    return round(der_val, 4), {
        "correct_s": round(best_correct, 3),
        "total_s": round(total, 3),
        "mapping": best_map,
        "n_gt_speakers": len(gt_spk),
        "n_hyp_speakers": len(hyp_spk),
    }


def jaccard_per_segment(gt: Sequence[Segment], hyp: Sequence[Segment]) -> float:
    """Mittlere segmentweise Jaccard-Ähnlichkeit (best-match je GT-Segment)."""
    gt = collapse(gt)
    hyp = collapse(hyp)
    if not gt or not hyp:
        return 0.0
    vals = []
    for g in gt:
        best = 0.0
        for h in hyp:
            inter = _overlap(g, h)
            union = max(g[1], h[1]) - min(g[0], h[0])
            j = inter / union if union > 0 else 0.0
            best = max(best, j)
        vals.append(best)
    return round(sum(vals) / len(vals), 4)


def speaker_count_error(gt: Sequence[Segment], hyp: Sequence[Segment]) -> int:
    return abs(len({s for _, _, s in gt}) - len({s for _, _, s in hyp}))


def rtf(infer_seconds: float, audio_seconds: float) -> float:
    return round(infer_seconds / audio_seconds, 4) if audio_seconds > 0 else 0.0


if __name__ == "__main__":
    # Selbsttest: perfekte Hypothese → DER 0; eine falsche Sprecher-Zuordnung
    # in der Mitte → DER > 0; fehlendes Segment → Missed.
    gt = [(0.0, 2.0, "A"), (2.0, 4.0, "B"), (4.0, 6.0, "A")]
    perfect = [(0.0, 2.0, "A"), (2.0, 4.0, "B"), (4.0, 6.0, "A")]
    d, det = der(gt, perfect)
    print(f"perfekt: DER={d} (erwartet 0.0)")
    assert d == 0.0, d

    wrong = [(0.0, 2.0, "A"), (2.0, 4.0, "A"), (4.0, 6.0, "B")]  # Mitte falsch
    d, det = der(gt, wrong)
    print(f"falsche Mitte: DER={d} (erwartet 0.3333…), detail={det}")
    assert abs(d - 1 / 3) < 0.001, d

    missing = [(0.0, 2.0, "A"), (4.0, 6.0, "A")]  # B-Segment fehlt
    d, det = der(gt, missing)
    print(f"fehlendes Segment: DER={d} (erwartet 0.3333…), detail={det}")
    assert abs(d - 1 / 3) < 0.001, d

    j = jaccard_per_segment(gt, perfect)
    print(f"Jaccard perfekt: {j} (erwartet 1.0)")
    assert j == 1.0, j
    print("SELBSTTEST OK")
