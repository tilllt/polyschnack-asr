# Change 196: Timing-Marker auf WaveSurfer RegionsPlugin umstellen

## Problem

Der Timing-Marker im Timing-Tab ist ein selbst gebautes `<div>` (Zeilen 436-477, `updateTimingMarker`), das manuell im Container positioniert wird. Daraus ergeben sich:

1. **Falsche Höhe**: Marker deckt den ganzen Canvas ab statt nur die sichtbaren Waveform-Balken (User: »doppelt so hoch wie die Waveform area«). Jeder Fix ist CSS-Patchwork, weil wir keine native Region-Höhe haben.
2. **Kein Touch/Mobile-Support**: Die selbst gebauten Drag-Handles funktionieren auf Mobilgeräten schlecht (User-Befund: »kann auf Mobilgerät nichts mehr markieren«).
3. **Doppelte Positionierungslogik**: `markerPct`/`visibleWindow` berechnen left/width in % des sichtbaren Fensters — WS `RegionsPlugin` macht das nativ.
4. **Wartungsaufwand**: ~100 Zeilen Custom-Code für etwas, das WS built-in kann.

## Lösung

Ersetze den Custom-DOM-Timing-Marker durch WS `RegionsPlugin.addRegion()`:

- `timingWord !== null` → `regions.addRegion({start: tw.start, end: tw.end, ...})`
- Drag-Events (`region.on('drag', ...)`) statt eigener Pointer-Event-Kette
- Constraints (`clampWordTiming`, `clampMoveWordTiming`) per `region.setOptions()` während Drag
- Commit per `region.on('dragend', ...)` → `onTimingCommit`
- Entfernt: `timingMarkerRef`, `updateTimingMarker`, `markerPct`, `visibleWindow`-Import
- Neu: `timingRegionRef` (Region-Objekt)

## Betroffene Dateien

- `frontend/src/components/WaveformPlayer.tsx` — Haupt-Refaktor
- `frontend/src/waveformTime.ts` — entfernt `markerPct`, `visibleWindow` (optional)

## Nicht betroffen

- Die Zoom-Logik (30%-Wort-Zoom, progressive Peaks) bleibt unverändert.
- Die Crop-Region (✂ Transcribe) bleibt ebenfalls per WS Region — sie wird bei `timingWord !== null` ausgeblendet.
- Die Constraint-Funktionen `clampWordTiming`, `clampMoveWordTiming` bleiben bestehen.
- `timeFromClick` bleibt (für Klick-Seek).

## Offene Fragen

- Bricht `region.setOptions({start, end})` während eines aktiven Drags den WS-internen Drag-State ab? → Workaround: erst beim `dragend` clammen, dann zurücksetzen mit visuellem Sprung.