# Change 142: Timing-Zoom — durchgehende Wellenform statt Balken

**Status:** Archived (auf specs/ angewendet, 2026-08-28)

## Problem (User-Befund 2026-08-28)

Im Timing-Modus (Wort herangezoomt, ~30 %-Regel, bis zu 2000 px/s) ist die
Waveform unlesbar: Die Balken-Optik (`barWidth: 2, barGap: 1, barRadius: 2`)
entartet beim starken Zoom zu gestreckten Strichen mit Lücken — man
erkennt die Wortstruktur nicht mehr.

## Ziel

Im Timing-Modus wird die Wellenform **durchgehend** dargestellt
(WaveSurfer rendert mit `barWidth: 0` eine gefüllte Kurve statt Balken);
beim Verlassen des Timing-Modus zurück zur Balken-Optik (Kopfraum-Design).

## Changes

- `WaveformPlayer.tsx` Timing-Zoom-Effekt: beim Aktivieren
  `w.setOptions({ barWidth: 0, barGap: 0, barRadius: 0 })` VOR `zoom()`
  (der Zoom rendert neu mit den Optionen); beim Verlassen zurück auf
  `barWidth: 2, barGap: 1, barRadius: 2`. `setOptions` in try/catch —
  nie den Zoom brechen.
- Verifikation: tsc, 378 Vitest, build.

## Downgrade

- setOptions-Aufrufe entfernen (Balken-Optik überall, Stand vor 142).
