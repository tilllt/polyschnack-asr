# Design — Change 083

## D1: Pure Helfer in `frontend/src/waveformTime.ts` (neu, testbar ohne WS7)

```ts
export const MIN_PPS = 0.05;                       // minPxPerSec für sehr lange Audios
export function fitPps(containerW: number, duration: number): number {
  return Math.max(MIN_PPS, containerW / Math.max(duration, 1));
}
export function timeFromClick(clickPx: number, scrollPx: number, pps: number, duration: number): number {
  const t = (scrollPx + Math.max(0, clickPx)) / Math.max(pps, MIN_PPS);
  return Math.max(0, Math.min(duration, t));
}
```

## D2: WaveformPlayer — Initial-Zoom = Fit

- `minPxPerSec: MIN_PPS` in `WaveSurfer.create(...)`.
- `ppsRef` (useRef<number>): aktuell angewandter px/s (fit oder Zoomstufe).
- `doZoom(ws, idx)`: `idx === 0 → pps = fitPps(containerW, ws.getDuration())`,
  sonst `pps = ZOOM_STEPS[idx - 1]`; `ppsRef.current = pps; ws.zoom(pps);
  setZoomIdx(idx); updateMarkers();`
- ready-Handler: die fitPps-/ZOOM_STEPS-Schleife ersetzen durch
  `doZoom(ws, 0)` (echter Fit, kein Runden auf 1 px/s).

## D3: WaveformPlayer — Klick-Seek scroll-/zoombewusst

```ts
const onContainerClick = (e: MouseEvent) => {
  if (!canPlayRef.current) return;
  const el = containerRef.current; if (!el) return;
  const rect = el.getBoundingClientRect(); if (rect.width <= 0) return;
  const dur = ws.getDuration(); if (!(dur > 0)) return;
  const scrollPx = ws.getScroll?.() ?? 0;
  const clickPx = e.clientX - rect.left;
  const t = timeFromClick(clickPx, scrollPx, ppsRef.current, dur);
  ws.setTime(t);
  ws.play();
};
```

Fit-Ansicht: `scrollPx = 0`, `clickPx / pps = ratio × dur` (Identität).
Gezoomt/gescrollt: absolute px-Position durch px/s.

## D4: Zoom-UI

- Label: `zoomIdx === 0 ? "fit" : `${ZOOM_STEPS[zoomIdx - 1]}×``
- „−" bei `zoomIdx <= 0` disabled (bleibt), „+" von fit → 1 px/s.

## D5: Tests

- `frontend/src/waveformTime.test.ts`:
  - Fit: `timeFromClick(400, 0, 0.14, 5710) ≈ 2855` (50 % der Dauer)
  - Gezoomt: `timeFromClick(400, 5000, 50, 600) = 108` (Scroll 100 s + 8 s)
  - Clamp auf [0, duration]
  - `fitPps`: Breite/Dauer, mind. MIN_PPS; lange Audio (5710 s) → < 1
- Bestehende Suiten (RecordingCard/Player-Mocks) müssen grün bleiben.
