"""Change 185 — Datenmigration: TTS-End-Marker aus Bestands-Transkripten entfernen.

Läuft im ps-webapp-Container (neues Image) gegen /data/app.db:
    python3 scripts/ps185_marker_migration.py --dry   # zeigt Funde
    python3 scripts/ps185_marker_migration.py         # schreibt

Scannt recording / transcriptionresult / transcriptversion und trimmt in
jeder Zeile mit Marker-Suffix (a) rec.text, (b) die letzten Segmente inkl.
deren Wort-Timing-Listen (words) — identische Logik wie die Pipeline
(_marker_suffix_trim / _trim_marker_word_run aus app.service, eine Quelle
der Wahrheit). Inhaltsscoped (nur found-Zeilen), idempotent, kein
Timestamp-/Versions-Schreiben.

Erwartung (Prod-Befund 2026-09-05): REC 318/322, TRES 133/149, VER 903-910/930.
"""
from __future__ import annotations

import json
import sqlite3
import sys

from app.service import _marker_suffix_trim, _trim_marker_word_run

DB = "/data/app.db"
TABLES = ("recording", "transcriptionresult", "transcriptversion")


def _clean_segments(segs_json: str | None) -> tuple[str | None, bool]:
    """Letzte bis zu 4 Segmente suffix-trimmen (wie die Pipeline);
    reine Marker-Segmente fallen. Rückgabe (segments_json, changed)."""
    if not segs_json:
        return segs_json, False
    try:
        segs = json.loads(segs_json)
    except Exception as exc:
        print(f"  ! segments-JSON unlesbar ({exc}) — Zeile übersprungen")
        return segs_json, False
    if not isinstance(segs, list):
        return segs_json, False
    changed = False
    processed = 0
    i = len(segs) - 1
    while i >= 0 and processed < 4:
        seg = segs[i]
        if not isinstance(seg, dict):
            break
        raw = str(seg.get("text") or "").strip()
        trimmed, hit = _marker_suffix_trim(raw)
        if not hit:
            break
        processed += 1
        changed = True
        if trimmed.strip():
            seg["text"] = trimmed.strip()
            # Wort-Timing-Liste konsistent trimmen (Bestands-Runs tragen
            # die Marker-Wörter noch in words — Text allein reicht nicht).
            words = seg.get("words") if isinstance(seg.get("words"), list) else None
            words2, _w_hit = _trim_marker_word_run(words)
            if words2 is not None:
                seg["words"] = words2
            segs[i] = seg
            i -= 1  # vorheriges Segment prüfen
        else:
            del segs[i]  # reines Marker-Segment: fällt, i bleibt (Nachrücker)
    if not changed:
        return segs_json, False
    return json.dumps(segs, ensure_ascii=False), True


def main() -> int:
    dry = "--dry" in sys.argv
    con = sqlite3.connect(DB, timeout=15)
    con.execute("PRAGMA busy_timeout=10000")
    cur = con.cursor()
    total_rows = 0
    total_changed = 0
    for table in TABLES:
        rows = cur.execute(
            f"SELECT id, text, segments FROM {table} ORDER BY id"
        ).fetchall()
        table_changed = 0
        for row_id, text, segs_json in rows:
            new_text, text_hit = _marker_suffix_trim(text or "")
            new_segs, segs_hit = _clean_segments(segs_json)
            if not text_hit and not segs_hit:
                continue
            total_rows += 1
            table_changed += 1
            print(f"{table} id={row_id} text_run={text_hit} segs={segs_hit}")
            if not dry:
                cur.execute(
                    f"UPDATE {table} SET text=?, segments=? WHERE id=?",
                    (new_text, new_segs, row_id),
                )
        if table_changed:
            print(f"{table}: {table_changed} Zeile(n)")
        total_changed += table_changed
    if not dry:
        con.commit()
    print(f"{'DRY-RUN: ' if dry else ''}{total_changed} von {total_rows} Zeile(n) "
          f"mit Marker-Suffix gefunden")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
