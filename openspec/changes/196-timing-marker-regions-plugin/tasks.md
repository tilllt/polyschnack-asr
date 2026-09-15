# Change 196 — Tasks

## T1: TimingRegion-Ref + isTimingRegion-Dragging-Ref

- [ ] `timingMarkerRef` → `timingRegionRef: useRef<{remove:()=>void, setOptions:(o:Partial<...>)=>void, on:(...)=>void, ...} | null>(null)`
- [ ] `timingDraggingRef` → `isTimingDraggingRef: useRef(false)` (oder behalten)
- [ ] Referenz auf regionsPlugin: `regionsRef.current` (existiert bereits)

## T2: Timing-Word-Erstellungs-Effekt

- [ ] Wenn `timingWord` gesetzt wird → bestehende Timing-Region entfernen, neue mit `regions.addRegion({start: tw.start, end: tw.end, color: 'rgba(46,160,67,0.18)', drag: true, resize: true})` erstellen
- [ ] Region-Ref setzen
- [ ] Wenn `timingWord === null` → Timing-Region entfernen

## T3: WS Region Event-Bindung

- [ ] `region.on('drag-start', ...)` → `isTimingDraggingRef.current = true`
- [ ] `region.on('drag', (region, dT) => ...)` — bei Handle-Drag (resize) oder Body-Drag (move) die constraint-checked Werte per `region.setOptions()` setzen + `onTimingChange` feuern
- [ ] `region.on('drag-end', ...)` → `isTimingDraggingRef.current = false; onTimingCommit(live.start, live.end)`
- [ ] `region.on('click', ...)` → `e.stopPropagation()` (damit Container-Klick-Seek nicht feuert)

## T4: Crop-Region-Interaktion anpassen

- [ ] Wenn `timingWord !== null` → Crop-Region ausblenden (bisher)
- [ ] Zusätzlich: Wenn `timingWord === null` → Timing-Region entfernen, Crop wiederherstellen

## T5: Alten Code entfernen

- [ ] `updateTimingMarker`-Callback löschen (Zeilen 436-477)
- [ ] `updateTimingMarkerRef` löschen
- [ ] `onTimingPointerDown` löschen (Zeilen 380-434)
- [ ] `timingMarkerRef` löschen
- [ ] `markerPct`-Import löschen
- [ ] `visibleWindow`-Import löschen

## T6: doZoom anpassen

- [ ] `updateTimingMarkerRef.current?.()` durch `regionsRef.current?.getRegions()?.filter(...)` ersetzen (oder direkt das timingRegionRef prüfen — WS aktualisiert Region-Position automatisch bei Zoom, also ggf. gar kein extra Call nötig)

## T7: Build-Test

- [ ] `npm run build` → exit 0

## T8: Validierung im Browser

- [ ] Timing-Tab: Wort klicken → Region erscheint auf der Waveform (korrekte Höhe)
- [ ] Drag an Handle → start/end ändert sich, Constraints greifen
- [ ] Body-Drag → ganze Markierung verschiebt sich, Constraints greifen
- [ ] Loslassen → `onTimingCommit` feuert
- [ ] Zoom/Scroll → Region bleibt korrekt positioniert
- [ ] Timing-Word abwählen → Region verschwindet, Crop-Region erscheint wieder
- [ ] Mobile Touch: Drag funktioniert