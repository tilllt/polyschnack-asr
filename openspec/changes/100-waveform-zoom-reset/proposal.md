# Change 100 — Waveform-Zoom springt zurück auf „fit"

## Problem

User-Befund: „zoom bei wavesurfer funktioniert nicht, wenn man reinzoomt
springt er sofort wieder heraus."

Reproduziert (Playwright, perfdata-Recording, Hauptseite): Klick auf
Zoom-in → Label wechselt auf „1×" → nach ~300 ms springt es zurück auf
„fit". Der Reset passiert genau in dem Fenster, in dem der asynchrone
Detail-Fetch (Recording-Detail + annotations) eintrifft.

## Root Cause

Der Initial-Zoom-Effekt in `WaveformPlayer.tsx`:

```ts
useEffect(() => {
  if (ready && !error && wsRef.current) {
    doZoom(wsRef.current, 0);   // ← 0 = „fit"
  }
}, [ready, error, doZoom]);
```

`doZoom` ist ein `useCallback` mit Dependency `[updateMarkers]`, und
`updateMarkers` hängt an `[annotations, ready, duration]`. Seit Change 059
kommen Peaks/Annotations **asynchron** über den Detail-Fetch nach (lite-Liste).
Sobald `annotations` eintrifft (nach `ready`), bekommt `doZoom` eine neue
Referenz → der ready-Effekt feuert **erneut** → `doZoom(0)` setzt den Zoom
zurück auf „fit" — jeder User-Zoom, der vor dem Eintreffen der späten Daten
erfolgt, wird sofort verworfen. Jede spätere Änderung der Annotationen
(Autosave) würde den Zoom ebenfalls zurücksetzen.

## Fix

Der Initial-Zoom darf **genau einmal** laufen: `initialZoomRef`-Guard im
Effekt. Der Change-083-Fall (Container erst nach `ready` sichtbar) bleibt
abgedeckt, weil der Effekt beim ersten `ready` nach dem React-Commit läuft
und der Container dann bereits sichtbar ist (kein späteres
Sichtbarwerden nach `ready` — Lazy-Load mountet den Player erst im
Viewport, Change 052/072).

## Zweiter Pfad (Firefox-Befund 2026-08-23): „Error: No audio loaded"

User-Konsolenbefund auf whisper.cia-spandau.de: `zoom()` wirft
`Error: No audio loaded` (WS7: kein `decodedData`). Der `ready`-STATE
kann true sein, während `wsRef.current` noch kein Audio geladen hat:
Change 059 re-initialisiert den Player, wenn Peaks asynchron nachkommen
(destroy + neuer `WaveSurfer` + `load()` läuft) — `setReady(true)`
bleibt vom ALTEN ws stehen. Ein `doZoom`-Aufruf in diesem Fenster
(ready-Effekt bei doZoom-Referenz-Wechsel ODER Zoom-Button-Klick, die
Buttons sind sichtbar weil `ready && !error`) ruft `ws.zoom()` auf dem
ladenden ws auf → Exception im Effekt/Handler.

Fix: `wsReadyRef` — im `ready`-Handler (echtes Audio geladen) auf true,
beim Init-Effekt-Start (neuer ws) auf false; `doZoom` bricht ab, wenn
nicht true. Der Initial-Fit bleibt unblockiert (der ready-Handler setzt
das Ref VOR dem Effekt-Lauf nach dem Commit).

## Tests

- Frontend-Unit-Test (WaveSurfer-Mock): Player mounten, ready abwarten,
  `zoom()`-Aufrufe zählen; dann `annotations`-Prop asynchron ändern →
  Assert: `ws.zoom` wird NICHT erneut mit Fit-Wert aufgerufen, Zoom-Label
  bleibt auf der User-Stufe.
- Re-Init-Szenario (Change 059): Peaks nachliefern → neuer ws ohne ready
  → Zoom-Klick ruft `ws.zoom()` NICHT auf (kein „No audio loaded"); nach
  dem neuen ready zoomen die Buttons wieder.
- Live-Verifikation: Playwright-Repro — nach Fetch-Ende bleibt der
  zweite Zoom-In stabil.
