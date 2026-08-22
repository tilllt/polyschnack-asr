# Tasks — Change 087: Frontend-Performance

## Phase 1: Dependency + Virtualisierung
- [x] `@tanstack/react-virtual` installieren (frontend/package.json + Lockfile)
- [x] SegmentList: `useVirtualizer` auf containerRef (max-h + fillHeight-Varianten)
- [x] Zeilen-Rendering auf `virtualizer.getVirtualItems()` umstellen (translateY)
- [x] rowRefs auf sichtbare Zeilen umstellen; Auto-Scroll/Such-Sprung via scrollToIndex
- [x] measureElement für dynamische Zeilenhöhen (Riesen-Zeilen)

## Phase 2: Wort-Spans bei Bedarf
- [x] renderWordSpans-Bedingung (Karaoke/Suche/Touch/Annotation/Split-Anker)
- [x] Fließtext-Fallback rendern (Optik identisch)
- [x] Markierungs-Flow: Spans beim Markieren aktivieren (Split + Touch)
- [x] React-key-Fix: Wort-Fragments mit key („Each child in a list"-Warnung)

## Phase 3: Tests + Verifikation
- [x] Bestehende Frontend-Suite grün (290 Tests, inkl. SegmentList.lock/annotate/split)
- [x] jsdom-Fallback (clientHeight 0 → renderAll) für Test-Umgebung
- [x] `tsc -p tsconfig.json` + `vite build`
- [x] perf90-auth.mjs NACHHER-Messung (Live-Daten, CPU 4×, Mobile 390×844):
  - Expand: 11 LT/2,8 s/35 FPS → **1 LT/62 ms/51,7 FPS**
  - Scroll: 8 LT/2,6 s/30 FPS → **1 LT/55 ms/53,7 FPS**
  - DOM: 5.599 Knoten/2.508 Spans → **400 Knoten/86 Spans**

## Phase 4: Abschluss
- [ ] OpenSpec-Change-Dateien final (Ergebnisse in proposal.md)
- [ ] Commit + Push + CI-Check

## Offener Befund (separater Change, nicht hier)
- [ ] Seiten-Load noch 2,9 s Long-Task-Last (26,8 FPS) — Karten-Waveform/Audio-
      Preview wird beim Initial-Load geladen (kollabierte Karte). Waveform-Lazy-
      Load prüfen (Change 089).

## Folge-Change 088 (separat)
- [ ] Backend: Segment-Re-Segmentierung auf ≤ 15 s-Blöcke (48 Riesen-Segmente)
      — nur Struktur, Text unverändert; wirkt zusammen mit 087
