# Change 055 — Tasks

## Phase 1: SegmentList.tsx
- [x] Prop `onSegmentInsert` (Doku + Typ + Destrukturierung) entfernen
- [x] Grenz-Leiste: nur noch Hairline (`h-px flex-1 bg-border/60`), ohne
      Button, `py-0`, kompakt; `prevHasWords` entfällt
- [x] „−"-Button unverändert lassen

## Phase 2: RecordingCard.tsx
- [x] `handleSegmentInsert` entfernen, Prop-Übergabe `onSegmentInsert` raus
- [x] Unbenutzten `insertSegment`-Import entfernen

## Phase 3: Qualität
- [x] `tsc --noEmit` sauber; vitest vollständig grün (SegmentList/RecordingCard-Tests)
- [ ] OpenSpec-Tasks abhaken, Commit + Push, CI prüfen und melden
