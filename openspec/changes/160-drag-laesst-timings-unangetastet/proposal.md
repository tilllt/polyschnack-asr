# Change 160 — Grenz-Drag lässt Wort-Timings unangetastet; Text-Edit gleicht Wörter an

**Status:** Proposed

## User-Regel (2026-08-30, bei Recording 8976aa1b beobachtet)

„Ein Segment-Drag soll die Wort-Timings nicht beeinflussen, AUSSER sie
werden manuell verändert." Der Grenz-Drag ist eine reine
Struktur-Operation (Segment-Zuordnung); Wort-Zeiten ändern nur manuelle
Timing-Edits (Change 137/155) oder Re-Align.

## Befund (Recording 297, live in der DB)

Nach Grenz-Verschieben + Satz-Umsortierung: Segmente mit DEUTSCHEN
Texten aber RUSSISCHEN Wörtern + linear verteilten Zeiten (exakt
1,5916 s/Wort). Playback/Karaoke zeigt die falschen Wörter/Zeiten
(User: „Timing total zerhauen, z.B. bei 06:23").

## Root Cause

- Der Drag-Pfad selbst (`moveBoundary` → `buildSeg` → `replace_segments`)
  ändert KEINE Wort-Zeiten (Objekte wandern unverändert, PUT speichert
  1:1).
- **Lücke:** Seit Change 125 laufen Text-Edits über denselben vollen
  Listen-PUT (`replaceSegments`) — der gleicht die Wörter NICHT an die
  neuen Texte an (kein `_align_words`/`reconcile_words_to_text`). Text
  und Wörter divergieren; der nächste Grenz-Drag persistiert den Desync.
- Lineare Zeiten stammen aus `_build_word_stream` (ASR-Wort-Erzeugung),
  nicht aus dem Drag.

## Lösung

`reconcile_words_to_text` (Change 140, aus `update_result` bekannt) auch
in `replace_segments` VOR dem Persistieren anwenden:

- **Reiner Grenz-Drag** (Text == join(words)) → No-Op, Wort-Objekte und
  Timings bleiben exakt erhalten (User-Invariante).
- **Text-Edit** (Text ≠ Wörter) → Wörter per LCS an den Text angleichen:
  Matches behalten ihre akustischen Zeiten, neue Text-Wörter werden
  interpoliert, Fremdwörter entfernt (Change-010-Semantik). Der Text ist
  die Wahrheit (Change-140-Prinzip) — im manuellen Edit-Fall gewollt.

## Tests

1. Grenz-Drag-PUT: konsistente Segmente → Wörter/Timings bitte-identisch
   (kein Wort wird angefasst).
2. Text-Edit-PUT: neuer Text → Wörter folgen dem Text (Matches behalten
   Zeiten, neue Wörter interpoliert).
3. Desync-Heilung: Segment mit Text ≠ Wörtern → nach PUT `join(words) == text`.
