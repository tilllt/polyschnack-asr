# Change 091 — Wort-Klick: Markierung aufräumen + Playback ab dem Wort

**Status:** in Arbeit → fertig (2026-08-22)
**Vorgabe (User, 22.08.):** „Einfacher klick (ohne drag, ohne doppelclick)
sollte evtl. vorhandene Markierungen im Transkript entfernen und Playback
bei dem Wort starten. Audio spielt ab dem Wort, Playbackmarker springt zu
der Zeit des Wortes auf der Waveform."

## Verhalten vorher (Change 077-Semantik)

Aktive Text-/Touch-Markierung blockierte jeden Klick in der betroffenen
Zeile: kein Playback, Markierung blieb unbegrenzt bestehen. Ein einfacher
Klick auf ein Wort tat nichts, solange eine (alte) Markierung existierte.

## Neues Verhalten (SegmentList.tsx)

- **Einfacher Klick** auf ein Wort oder eine Zeile (ohne Drag, ohne
  Doppelklick): räumt vorhandene Markierungen weg (Touch-Selection +
  native Browser-Textmarkierung, `clearTextSelection`) und startet
  Playback an der Wort-Zeit (`onSeekTo(w.start)` → Waveform-Seek + Play,
  Marker springt zur Wort-Zeit).
- **Klick direkt nach einem Text-Drag** (Drag-Ende über
  `handleTextMouseUp`/`handleTextPointerUp` setzt `dragMadeRef`, 500 ms):
  behält die Markierung für Split/Annotate — kein Playback, keine
  Zerstörung der frisch gezogenen Auswahl.
- Doppelklick/Doppeltap (Edit-Modus) und Annotation-Klick bleiben
  unverändert (kein Playback).

## Verifikation

- 291 Frontend-Tests grün (2 neue: „einfacher Klick räumt Markierung auf
  + startet Playback", „Klick nach Drag behält Markierung, kein Playback")
- Browser (lokal, echte Daten): Klick auf ein Wort → Anzeige springt auf
  die Wort-Zeit, playing: true („4:34 / 95:10").
