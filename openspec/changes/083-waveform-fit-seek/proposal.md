# Change 083 — Waveform: Initial-Zoom = 100 % + klick-genaues Seek

## Problem (User-Befund 22.08.2026)

„In die Waveform klicken springt zu weit entfernte Stellen. Solange man
nicht ranzoomt soll die Timeline 100 % der Audiolänge zeigen."

**Root Cause (verifiziert im Code):**
1. **Initial-Zoom ist kein Fit.** `ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50]`
   (px/s) und `minPxPerSec: 1`; der ready-Handler wählt den größten
   `ZOOM_STEPS[i] <= max(1, Breite/Dauer)`. Bei langen Audios (z. B.
   5710 s, 800 px) ist fitPps = 1 → Zoom = 1 px/s → nur ~14 % der
   Audiolänge sichtbar, die Timeline zeigt nie 100 %.
2. **Klick-Seek ignoriert Zoom/Scroll.** Der eigene Click-Handler
   (Change 077, `interact: false`) rechnet `ratio × Dauer` über die
   sichtbare Breite — korrekt nur bei Fit-Ansicht. Bei gezoomter oder
   gescrollter View springt der Klick auf eine völlig andere Stelle
   (50 % des Sichtbaren = 50 % der Gesamtdauer).

**Verifiziert korrekt (nicht Teil des Bugs):** Wort-Klick → Playback,
Karaoke-Highlight und Cursor nutzen dieselbe Zeitbasis (Segmente werden
nach VAD-Trim auf Original-Basis aufgeschlagen, service.py Z. 1620–1629;
Playback spielt die Originaldatei; Karaoke liest `getCurrentTime`).

## Lösung

- Initial-Zoom = exakter Fit (`Breite / Dauer`), auch für lange Audios
  (`minPxPerSec` auf 0.05 gesenkt). Zoom-Index 0 = „fit"; „+" zoomt auf
  1 px/s, „−" zurück auf fit.
- Klick-Seek rechnet mit `(ScrollPx + KlickPx) / pps` — korrekt bei Fit,
  Zoom UND Scroll.

## Nicht-Ziele

- Keine Änderung an interact-Gating, Karaoke-Lead, Wort-Timestamps.
- Kein Umbau der Zoom-Stufen (nur Index 0 = fit statt 1 px/s).
