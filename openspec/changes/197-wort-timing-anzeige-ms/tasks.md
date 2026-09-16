# Change 197 — Implementation

## Tasks

- [x] Ursache bestätigt: `fmtTimecode` rundet auf ganze Sekunden → Wortlänge 0,32 s zeigt `00:00`
- [x] `fmtShortTimecode()` in `src/format.ts` (MM:SS.sss)
- [x] `TimingEditor.tsx`: Start, Ende und Länge auf `fmtShortTimecode` umgestellt; ungenutzten `fmtTimecode`-Import entfernt
- [x] `format.test.ts`: Testfälle + Invariante (`fmtTimecode(0.32) === "00:00"` vs. `fmtShortTimecode(0.32) === "00:00.320"`)
- [x] `MAX_TIMING_PPS` 2000 → 48000 (`src/waveformTime.ts`) mit Begründung im Docstring
- [x] `waveformTime.test.ts`: Invariante „Mindest-Wortdauer erreicht 30 %-Zielfenster"; alter Clamp-Test auf 0.001 s / 0.0001 s angepasst
- [x] `MIN_WORD_DURATION_S`-Import ergänzt
- [x] Tests: **410 grün** (33 Dateien)
- [x] `npm run build`: exit 0
- [ ] Commit + Push
- [ ] CI-Pipeline abwarten
- [ ] Deploy auf KI-Box (`/opt/container/polyschnack`, compose up -d ps-webapp)
- [ ] Browser-Gegenprobe im Timing-Tab: Wortlänge zeigt Millisekunden, 20-ms-Wort füllt ~30 % der Breite

## Geänderte Dateien

- `frontend/src/format.ts`
- `frontend/src/format.test.ts`
- `frontend/src/components/TimingEditor.tsx`
- `frontend/src/waveformTime.ts`
- `frontend/src/waveformTime.test.ts`
