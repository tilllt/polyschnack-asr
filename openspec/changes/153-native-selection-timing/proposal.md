# Change 153 — Timing-Tab: native Textmarkierung nicht durch Klick-Logik zerstören

**Status:** Proposed (Umsetzung läuft)

## Problem (User-Befund 2026-08-29)

Im **Timing-Modus** (readOnly-Wortliste, TimingEditor) lässt sich Text
nicht mit Systemfunktionen markieren und kopieren: Die Klick-Logik der
SegmentList zerstört die Markierung bzw. löst ungewollte Aktionen aus.

Ursache (readOnly-Kontext, ohne Split/Annotate-Handler):

1. **Zeilen-Klick** (`handleClick`, via `scheduleClick` 280 ms): ruft
   `clearTextSelection()` → `window.getSelection()?.removeAllRanges()` —
   die frische Textmarkierung wird gelöscht, bevor man Ctrl+C drücken
   kann. Zusätzlich startet Playback-Seek (`onSeekTo`).
2. **Wort-Klick** (`handleWordClick`): im readOnly-Modus lädt JEDER Klick
   das Wort in die Waveform (`onWordClick`) — auch der Klick, der beim
   Loslassen einer Markier-Geste entsteht.
3. Der `dragMadeRef`-Schutz (Markierung behalten) wird nur von den
   Split-/Annotate-Handlern gesetzt — die existieren im Timing-Modus
   nicht (`onSplitSegment || onAnnotate` = false → Handler deaktiviert).

## Lösung

Native Textmarkierung hat Vorrang vor der Klick-Logik, **nur im
readOnly-Modus** (Timing-Tab bleibt Edit-View unverändert):

- Neuer Helper `hasNativeSelection()`: Selection existiert, nicht
  kollabiert, `rangeCount > 0`.
- `handleClick`: `if (readOnly && hasNativeSelection()) return;` — kein
  `clearTextSelection`, kein Seek, kein aktive-Zeile-Wechsel, solange
  eine Markierung aktiv ist. Klick ohne Markierung seekt weiter.
- `handleWordClick`: im readOnly-`onWordClick`-Zweig
  `if (hasNativeSelection()) return;` — die Markier-Geste lädt kein Wort
  in die Waveform. Klick ohne Markierung lädt weiter (Timing-Funktion).
- `clearTextSelection`: im readOnly-Modus native Selection NICHT löschen
  (nur `touchSel`) — Defense in Depth gegen künftige Aufrufer.

Damit bleibt die Markierung nach dem Loslassen stehen; Ctrl+C /
Kontextmenü → Kopieren funktioniert mit der Browser-Selection.

## Nicht-Änderung (User-Vorgabe 2026-08-29)

Der **Transkriptions-Modus (nicht-readOnly)** bleibt unverändert:
Split/Annotate-Markierung, dragMadeRef-Schutz, clearTextSelection beim
einfachen Klick, Doppelklick-Edit, Touch-Pfad — alles wie bisher. Alle
Guards sind strikt an `readOnly` gebunden; der Edit-View verhält sich
byte-identisch.
