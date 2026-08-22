# Change 087 — Frontend-Performance: SegmentList-Virtualisierung + Wort-Span-Lazy

**Status:** proposed → in Arbeit (2026-08-22)
**Problem:** 90–95-min-Aufnahmen machen die GUI auf Smartphones unbenutzbar.

## Gemessene Baseline (2026-08-22, Playwright, Mobile 390×844, CPU 4×)

Live-Daten (echtes 95-min-Recording, Box): 48 Segmente (Ø 119 s, max 287
Wörter/Zeile), 2.508 Wort-Spans, 212 KB Recording-JSON, 2.000 Peaks.

| Phase | Long-Tasks | max Block | FPS |
|---|---|---|---|
| Seiten-Load (eingeloggt) | 11 / 5,5 s | 998 ms | **2,2** |
| Karte expandieren | 11 / 2,8 s | 550 ms | 35 |
| Scrollen | 8 / 2,6 s | 691 ms | 30 |

- Share-Ansicht (ohne Wort-Spans): 53 FPS → **Wort-Spans sind der Hebel**.
- Synthetischer 2.500-Segment-Test: 20.063 DOM-Knoten, 3,1 MB HTML, 10 FPS.

## Ursachen

1. `SegmentList.tsx` rendert ALLE Segmente unvirtualisiert (kein Windowing).
   `rowRefs` hält Referenzen auf jede Zeile (Auto-Scroll, Drag, Split).
2. Wort-Spans (Z. 1346ff) werden gerendert, sobald `onSplitSegment` gesetzt
   ist (eingeloggte Ansicht = immer) — 2.508 Einzel-Spans mit Handlern,
   obwohl ohne aktives Playback/Suche/Markierung nur Fließtext sichtbar wäre.
3. Riesen-Segmente (Backend-Ausgabe): 48 × ~119 s — eine Zeile = 15–20
   Handy-Bildschirme. (Backend-Folgeaufgabe, siehe tasks.)

## Lösung (Entscheidung 2026-08-22)

1. **Virtualisierung der SegmentList** (`@tanstack/react-virtual`, windowing
   auf Zeilen-Ebene): nur sichtbare Zeilen + Overscan (2) im DOM. Bei 48
   Riesen-Zeilen = statt 2.508 nur ~300–600 Wort-Spans. Sichtbarer Gewinn
   auch bei vielen normalen Segmenten (2.500-Zeilen-Fall).
2. **Wort-Spans nur bei Bedarf rendern**: Playback aktiv (Karaoke),
   Such-Treffer, Touch-Selektion, Annotation in der Zeile — sonst Fließtext.
   Split-Markierung bleibt: Wort-Range wird beim Markieren aus der
   Text-Position berechnet (selectionCharRange/wordRangeToCharRange),
   die Spans werden nur während der aktiven Markierung gerendert.
3. **Kein Verhalten-Verlust**: Auto-Scroll (activeIdx/Wort), Drag-Grenzen,
   Touch-Markierung, Edit, Annotationen, Yjs — alles bleibt, nur die
   DOM-Menge wird begrenzt. Bestehende Tests (SegmentList.*, 290 Frontend)
   müssen unverändert grün bleiben.

## Erwartete Wirkung

- Seiten-Load: 5,5 s → < 1 s Long-Task-Last (Ziel: > 40 FPS in allen Phasen
  bei CPU 4×)
- Scrollen: 30 → > 45 FPS
- DOM: 5.599 → < 1.500 Knoten
- Messung identisch: `perf90-auth.mjs` / `perf90.mjs` (vorher/nachher)
