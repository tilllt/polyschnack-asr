"""Change 187: Wort-verankerte Segmentgrenzen (Anker-Invariante).

Die Wortliste eines Segments IST der Anker: hat ein Segment (verankerte)
Wörter, dann sind seine Grenzen ABGELEITET —

    seg.start = words[0].start
    seg.end   = start des ersten Wortes des FOLGESEGMENTS
                (letztes Segment bzw. Folge ohne Wörter: words[-1].end)

Damit ist die Grenze ein Schnitt in der globalen Wortfolge der Aufnahme: ein
Re-Align verschiebt die Wörter und damit automatisch die Grenzen; Überlappungen
zwischen Segmenten sind per Konstruktion ausgeschlossen (Naht-Fälle werden
monoton verklebt). Segmente OHNE Wörter (leerer Text, Altbestand) behalten ihre
gespeicherten Zeiten — die Invariante gilt nur, wo es Wörter gibt.

Reine Funktionen ohne DB-/HTTP-Abhängigkeit: nutzbar im Align-Pfad
(service.py), im Choke-Point (routers/segments.py:reconcile_words_to_text) und
in der Migration (Admin-Aktion mit Dry-Run-Bericht).
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Zeittoleranz für Vergleiche (Sekunden).
WORD_EPS = 1e-6

#: Ab dieser Änderung gilt ein Delta im Migrationsbericht als relevant.
REPORT_DELTA_S = 0.05


def _num(value: Any) -> Optional[float]:
    """Zahl oder None (bool zählt nicht als Zeitwert)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _word_time(word: Dict[str, Any], key: str) -> Optional[float]:
    return _num(word.get(key))


def anchored_words(segment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Wortliste nur, wenn sie als Anker taugt (erstes start + letztes end)."""
    words = segment.get("words") or []
    if not words:
        return []
    if _word_time(words[0], "start") is None:
        return []
    if _word_time(words[-1], "end") is None:
        return []
    return words


def glue_words_after(
    prev_end: Optional[float], words: Sequence[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], float]:
    """Naht-Regel: Wortliste hinter `prev_end` schieben, falls sie davor beginnt.

    Liefert `(words, delta)`. Echte Sprechpausen bleiben erhalten — nur
    Rückwärts-Überlappungen werden aufgelöst. Die Eingabe wird nicht verändert.
    """
    out = [dict(w) for w in words]
    if not out or prev_end is None:
        return out, 0.0
    first = _word_time(out[0], "start")
    if first is None or first >= prev_end - WORD_EPS:
        return out, 0.0
    delta = prev_end - first
    for item in out:
        ws, we = _word_time(item, "start"), _word_time(item, "end")
        if ws is not None:
            item["start"] = ws + delta
        if we is not None:
            item["end"] = we + delta
    return out, delta


def enforce_word_anchored_bounds(
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Anker-Invariante erzwingen (mutiert `segments`, gibt dieselbe Liste zurück).

    1. **Monotonie:** beginnt das erste Wort eines Segments vor dem Ende des
       Vorgängers (Naht zwischen zwei Align-Gruppen), wird die Wortliste des
       Segments als Ganzes hinter das Vorgänger-Ende geschoben (interne
       Abstände bleiben erhalten).
    2. **Ableitung:** `seg.start = words[0].start` und
       `seg.end = start des ersten Wortes des Folgesegments` (letztes Segment
       bzw. Folge ohne Wörter: `words[-1].end`).
    """
    prev_end: Optional[float] = None
    for seg in segments:
        words = anchored_words(seg)
        if not words:
            own_end = _num(seg.get("end"))
            if own_end is not None:
                prev_end = own_end if prev_end is None else max(prev_end, own_end)
            continue
        first = _word_time(words[0], "start")
        if prev_end is not None and first is not None and first < prev_end - WORD_EPS:
            words, _delta = glue_words_after(prev_end, words)
            seg["words"] = words
        seg["start"] = _word_time(words[0], "start")
        seg["end"] = _word_time(words[-1], "end")
        last_end = _word_time(words[-1], "end")
        if last_end is not None:
            prev_end = last_end if prev_end is None else max(prev_end, last_end)

    # Grenze am Start des ersten Wortes des Folgesegments.
    for idx in range(len(segments) - 1):
        cur = anchored_words(segments[idx])
        nxt = anchored_words(segments[idx + 1])
        if cur and nxt:
            nxt_first = _word_time(nxt[0], "start")
            if nxt_first is not None:
                segments[idx]["end"] = nxt_first
    return segments


def plan_bound_correction(segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Dry-Run-Bericht: was würde das Ableiten der Grenzen ändern? (read-only)

    Simuliert die Ableitung auf einer Kopie und vergleicht mit dem Ist-Stand.
    """
    before = [
        (_num(seg.get("start")), _num(seg.get("end"))) for seg in segments
    ]
    sim = copy.deepcopy([dict(seg) for seg in segments])
    for idx, seg in enumerate(sim):
        seg["words"] = [dict(w) for w in (seg.get("words") or [])]
        _ = idx
    enforce_word_anchored_bounds(sim)

    report: Dict[str, Any] = {
        "segments": len(segments),
        "with_words": 0,
        "without_words": [],
        "bounds_changed": [],
        "shifted": [],
        "overlaps": [],
        "max_start_delta_s": 0.0,
        "max_end_delta_s": 0.0,
        "actionable": False,
    }
    for idx, (seg, (b_start, b_end)) in enumerate(zip(sim, before)):
        a_start, a_end = _num(seg.get("start")), _num(seg.get("end"))
        if not anchored_words(seg):
            report["without_words"].append(idx)
            continue
        report["with_words"] += 1
        old_words = (segments[idx].get("words") or [])
        new_words = seg.get("words") or []
        if old_words and new_words:
            ow = _word_time(old_words[0], "start")
            nw = _word_time(new_words[0], "start")
            if ow is not None and nw is not None and abs(nw - ow) > WORD_EPS:
                report["shifted"].append({"segment": idx, "delta_s": round(nw - ow, 3)})
        ds = abs((a_start or 0.0) - (b_start or 0.0))
        de = abs((a_end or 0.0) - (b_end or 0.0))
        report["max_start_delta_s"] = round(max(report["max_start_delta_s"], ds), 3)
        report["max_end_delta_s"] = round(max(report["max_end_delta_s"], de), 3)
        if ds > REPORT_DELTA_S or de > REPORT_DELTA_S:
            report["bounds_changed"].append(
                {
                    "segment": idx,
                    "start_before": b_start,
                    "start_after": a_start,
                    "end_before": b_end,
                    "end_after": a_end,
                    "delta_end_s": round((a_end or 0.0) - (b_end or 0.0), 3),
                }
            )
    for idx in range(len(before) - 1):
        a_end = before[idx][1]
        b_start = before[idx + 1][0]
        if a_end is not None and b_start is not None and b_start < a_end - REPORT_DELTA_S:
            report["overlaps"].append(
                {"boundary": idx, "overlap_s": round(a_end - b_start, 3)}
            )
    report["actionable"] = bool(report["shifted"] or report["bounds_changed"])
    return report


def resolve_zero_durations(
    words: Sequence[Dict[str, Any]], cap: float = 1.0
) -> List[Dict[str, Any]]:
    """Change 152: Wörter mit end=start (Dauer 0) oder ≤ 50 ms bekommen eine
    Dauer aus dem Start des Folgeworts — aber NIE über eine Stille-Lücke
    (> 0,5 s) hinweg; dann greift die harte Maximaldauer `cap`. Das letzte
    Wort einer Liste bekommt ebenfalls `cap`. Eingabe bleibt unverändert.
    """
    out = [dict(w) for w in words]
    for i in range(len(out) - 1):
        w = out[i]
        ws, we = _word_time(w, "start"), _word_time(w, "end")
        if ws is None:
            continue
        if we is None or we - ws <= 0.05:
            nxt = _word_time(out[i + 1], "start")
            if nxt is not None and nxt - ws <= 0.5:
                out[i]["end"] = nxt
            else:
                out[i]["end"] = ws + cap
    if out:
        w = out[-1]
        ws, we = _word_time(w, "start"), _word_time(w, "end")
        if ws is not None and (we is None or we - ws <= 0.05):
            out[-1]["end"] = ws + cap
    return out


def assign_words_by_index(
    spans: Sequence[Tuple[int, int]],
    aligned_words: Sequence[Dict[str, Any]],
) -> Tuple[Dict[int, List[Dict[str, Any]]], Optional[str]]:
    """Align-Wörter per WORTINDEX den Segmenten zuordnen (Change 187).

    `spans` = [(segment_index, wortzahl), …] in Textreihenfolge (ein langes
    Segment kann mehrfach vorkommen, wenn es intern gechunkt wurde).
    `aligned_words` = Wörter des Aligners für den Gruppentext, in Reihenfolge.

    Regel: das erste Segment der Gruppe bekommt die ersten `wortzahl` Wörter,
    das nächste die folgenden usw. — der Aligner liefert genau ein Wort je
    Eingabewort (Wortzahl rein = Wortzahl raus); Textähnlichkeit (LCS) wird
    NICHT gebraucht.

    Rückgabe `(words_by_segment, fehler)`; bei Wortzahl-Mismatch wird nicht
    geraten: `fehler == "word_count_mismatch"` und leere Zuordnung.
    """
    total = sum(int(n) for _, n in spans if n and n > 0)
    if len(aligned_words) != total:
        return {}, "word_count_mismatch"
    out: Dict[int, List[Dict[str, Any]]] = {}
    cursor = 0
    for seg_idx, n in spans:
        n = int(n or 0)
        if n <= 0:
            continue
        chunk = [dict(w) for w in aligned_words[cursor:cursor + n]]
        cursor += n
        out.setdefault(int(seg_idx), []).extend(chunk)
    return out, None
