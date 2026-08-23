# Change 101 — Re-Align meldet ehrlich, wenn keine Wörter ersetzt wurden

## Problem

User-Befund (2026-08-23): Bei „saisoncouplet.mp3" bringt Re-Align
garnichts — das Karaoke-Timing „rast" in einem Rhythmus durch den Text,
der nichts mit der Sprache zu tun hat.

Reproduziert über die Produktions-API (Recording 295, uid
49b7b10acd1245a58600863e9b076581):

- Die Wort-Timestamps sind ein **fixes 80-ms-Raster** (408/425 Deltas =
  exakt 0.08 s; Wörter füllen das Segment nur zu ~20 %). Diese Rasterung
  kommt aus den Backend-Token-Platzhaltern (`_merge_token_words`), die
  der Forced-Aligner eigentlich ersetzen soll.
- `POST /realign` → 200, `alignment: pending → running → done` (Lauf
  < 30 s), aber die Wörter sind **100 % identisch zu vorher**.

## Root Cause

`_run_background_align` (service.py) setzt `alignment = "done"`, sobald
`_run_align_phase` Segmente zurückgibt — **auch wenn diese unverändert
sind** (kein einziges Wort ersetzt). `_run_align_phase` gibt die
Original-Segmente zurück, wenn der Aligner nicht erreichbar ist
(`client.health()` false), alle Gruppen-Fehler wirft oder keine Wörter
liefert. Ergebnis: Der User sieht „Re-Align fertig" (done), aber die
Timestamps bleiben die 80-ms-Rasterung → Karaoke „rast" — ein stiller
Fehler (UI-Regel: stille Fehler inakzeptabel).

## Fix

1. **Backend:** `_run_background_align` setzt `done` NUR, wenn sich die
   Wörter wirklich geändert haben. Bleiben sie identisch
   (`_same_segments(new_segments, segments)`), wird `alignment =
   "skipped"` gesetzt und `error` mit dem Grund befüllt:
   - Aligner nicht erreichbar (`AlignerClient().health()` false)
   - sonst: „Aligner lieferte keine Wort-Timestamps"
2. **UI:** Der Alignment-Status wird sichtbar — bei `skipped` ein
   Hinweis am Re-Align-Button („Alignment übersprungen — Wort-Timestamps
   unverifiziert", Tooltip mit Grund); bei `running` ein Lauf-Hinweis.

Damit ist nach einem Re-Align sofort sichtbar, dass der Aligner nichts
geliefert hat (und warum) — statt einer stillen „done"-Lüge.

## Offen (separate Frage)

Warum genau der Aligner für diese Datei nichts liefert (Container down
vs. Align-Fehler) wird nach dem Deploy über den neuen `error`-Grund
ablesbar; die Aligner-Logs auf der ki-box bleiben die zweite Quelle.

## Tests

- Backend: `_run_background_align` mit Aligner, der nichts liefert
  (health false / leere Wörter) → `alignment == "skipped"` + `error`
  gesetzt; mit lieferndem Aligner → `done` + Wörter ersetzt.
- Frontend: RecordingCard zeigt bei `alignment == "skipped"` den
  Hinweis an.
