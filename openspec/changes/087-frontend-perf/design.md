# Design — Change 087: SegmentList-Virtualisierung

## 1. Technik: `@tanstack/react-virtual`

- Kleine, getestete Library (kein Vendor-Patch nötig, Dependency + Lockfile).
- `useVirtualizer({ count: segments.length, getScrollElement: () => containerRef.current, estimateSize: () => 48, overscan: 2 })`.
- containerRef (bestehender Scroll-Container, `max-h`/`fillHeight`-Varianten)
  wird zum Scroll-Element; Zeilen werden absolut positioniert
  (`transform: translateY(virtualRow.start)`), Höhe = virtualRow.size
  (measureElement für dynamische Zeilenhöhen — Riesen-Zeilen!).
- `rowRefs` bleibt für die sichtbaren Zeilen (Map index → el) —
  Auto-Scroll/Such-Sprung über `virtualizer.scrollToIndex(idx, {align:"center"})`
  statt manuellem `container.scrollTo` (scroll-smooth bleibt).

## 2. Wort-Spans nur bei Bedarf

Bedingung (ersetzt Z. 1346ff):
```
renderWordSpans =
  (currentTime != null && i === activeIdx)        // Karaoke/Playback
  || hasSearch                                    // Such-Hervorhebung
  || (touchSel?.idx === i)                        // Touch-Markierung aktiv
  || (annotations?.some(a => a.segment_idx === i))// Annotation in Zeile
  || (splitAnchor?.idx === i)                     // Split-Markierung aktiv
```
Sonst: Fließtext (`seg.text`) — Optik identisch (confidenceClass liefert "").

- Split/Markieren funktioniert weiter: Beim Markieren (pointerdown/up,
  mouseup) werden die Wort-Spans der Zeile ON DEMAND gerendert
  (`splitAnchor`/`touchSel`-State) — die Wort-Range-Berechnung
  (wordRangeToCharRange) arbeitet auf `seg.words` (Daten), nicht DOM.
- Regression-Risiko (Fix 2026-08-18 „Split ging erst nach Playback"): durch
  Markierungs-Trigger abgesichert — Test `SegmentList.split.test` deckt ab.

## 3. Auto-Scroll / Such-Sprung

- `activeIdx`-Effekt: `virtualizer.scrollToIndex(activeIdx, { align: "center" })`
  + aktives Wort via `data-active-word` im sichtbaren Bereich.
- `searchJump`: `scrollToIndex(searchJump.idx)`; Edit-Modus-Guard bleibt.
- Drag-Grenzen/Split-Popover: nutzen `rowRefs.current[i]` — nur sichtbare
  Zeilen existieren; Popover-Koordinaten über `virtualizer.measureElement`
  (getBoundingClientRect des gemessenen Elements).

## 4. Kein Verhalten-Verlust

- Alle bestehenden Tests (SegmentList.lock/annotate/split, RecordingCard,
  karaoke, resegment) bleiben unverändert grün; Vitest-mockt keinen
  Virtualizer → Tests rendern die Liste im jsdom-Container (kleine
  Test-Fixtures: < Overscan → alle Zeilen sichtbar, Verhalten identisch).
- jsdom: `getScrollElement` liefert Container mit scrollHeight 0 →
  `virtualizer` rendert initial Overscan-Zeilen; Tests mit wenigen
  Segmenten sehen weiterhin alle.

## 5. Abgrenzung

- NICHT in diesem Change: Backend-Re-Segmentierung (48 Riesen-Segmente).
  Folge-Change 088 (Backend): Segmente nach Wort-Timestamps auf
  ≤ 15 s-Blöcke nachsegmentieren (nur Anzeige/Struktur, Text unverändert).
- Waveform (2.000 Peaks) separat beobachten — bisher kein Befund.
