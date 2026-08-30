# Change 158 — Align-Fehler ehrlich melden (skipped mit Grund)

**Status:** Proposed

## Befund (2026-08-30, User-Anforderung „das gleiche gilt für align")

Ein ASR-Run darf nicht abbrechen, weil der Aligner-Container nicht läuft.
Code-Befund (bereits erfüllt):
- `process_recording` kontaktiert den Aligner NIE synchron (Change 045:
  Alignment startet nach `done` als Hintergrund-Job `kind=align`).
- `_run_background_align` failt nie: Aligner-Fehler → `alignment="skipped"`,
  Backend-Timestamps bleiben, Transkription bleibt done.

**Lücke (halbstiller Fehler):** Im Fehlerpfad `new_segments is None`
(Aligner-Call warf, z.B. Container down) wird `rec.alignment="skipped"`
gesetzt, aber **kein `rec.error`** — der User sieht „Alignment skipped"
ohne Grund. Der verwandte Fall „Aligner lieferte 0 Wörter" setzt dagegen
`rec.error` mit Health-Check-basiertem Grund (Zeile 1463-1469).

## Lösung

1. `_run_background_align`, `else`-Zweig (`new_segments is None`): Grund per
   `AlignerClient().health()` ermitteln und `rec.error` setzen —
   „Alignment übersprungen: Aligner nicht erreichbar" / „…: Aligner-Fehler"
   (symmetrisch zum 0-Wörter-Fall). Kein stiller Fehler (User-Regel).
2. Test: Aligner-Call wirft (down) → `alignment="skipped"` + `error` mit
   Grund, Recording-Status bleibt `done`.
