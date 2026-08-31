# Change 168 — Tasks

- [x] Befund: 400 "missing start/end" (undefined-Key verschwindet im JSON),
      stille No-Op-Folgeversuche (ganze-Segment-Markierung).
- [x] `ensureSegmentBounds` in resegment.ts (Wort-/Nachbar-Fallback).
- [x] Einbau in persistSegmentList + handleBoundaryDragEnd (vor PUT).
- [x] `handleSplitSegment`: No-Op mit Toast (i18n split_noop, de/en/pt).
- [x] Tests: ensureSegmentBounds (Wort-/Nachbar-/unverändert-Fälle).
- [ ] Lokale Frontend-Tests grün (resegment.test.ts).
- [ ] openspec/change 168 committen, push main, CI grün.
- [ ] Deploy; Live-Test durch User (Split mit Teil-Markierung).
