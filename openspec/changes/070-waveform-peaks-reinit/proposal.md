# Change 070 — Waveform-Peaks-Nachladen: Re-Init statt ewiges „Loading"

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User-Befund (2026-08-21): „Seit du die Seite für langsame Verbindungen
beschleunigt hast hängen für immer die waveforms in 'loading waveforms'
fest."

Root Cause: Change 059 (lite-Liste) liefert `waveform_peaks: null` in der
Liste — die Peaks kommen erst **asynchron** über den Detail-Fetch
(`useRecordingDetail`) nach. Der WaveSurfer-Init-Effekt in
`WaveformPlayer` hing aber nur von `[audioUrl, backend, inView]` ab —
**`peaks`/`durationHint` fehlten in den Dependencies**. Der Player
startete also mit `peaks=null` und ging in den Browser-Decode-Pfad
(ganze Datei laden + dekodieren — auf langsamen Verbindungen dauert das
sehr lange bzw. schlägt fehl); trafen die Server-Peaks dann ein, wurde
der Effekt **nie neu gestartet** → „Loading waveform…" für immer.

## Ziel

1. WaveSurfer wird neu initialisiert, sobald die Server-Peaks eintreffen:
   `peaks` + `durationHint` als Effect-Dependencies → Mini-Preview statt
   Voll-Decode.
2. Timer-Cleanup beim Re-Init (kein verwaister loadTimeout vom ersten
   Lauf, der nach dem Re-Init fälschlich „corrupted" meldet).
3. Kein Player-Leak beim Re-Init (destroy des alten WaveSurfer).

## Verhaltens-Delta (IST → SOLL)

- **IST:** Player startet mit peaks=null → Voll-Decode-Pfad; Peaks
  kommen nach → kein Re-Init → „Loading waveform…" hängt ewig.
- **SOLL:** Peaks treffen ein → Effekt läuft neu → `ws.load(url,
  [peaks], duration)` → Waveform sofort sichtbar (Mini-Preview, Change
  059-Pfad funktioniert).

## Umsetzung

1. `WaveformPlayer.tsx`: Init-Effect-Dependencies um `peaks` +
   `durationHint` erweitert; Cleanup cleart `timerRef` (loadTimeout).
2. Tests: `WaveformPlayer.peaks.test.tsx` (4): ohne Peaks → load
   undefined; mit Peaks → [peaks]+duration; nachträgliche Peaks →
   Re-Init (2. create + 2. load mit Peaks); alter Player wird destroyed.

## Referenzen

- Change 059 (lite-Liste, Peaks nachladen), Change 052 (Lazy-Loading)
- `WaveformPlayer.tsx` Zeile ~535 (Effekt-Dependencies)
