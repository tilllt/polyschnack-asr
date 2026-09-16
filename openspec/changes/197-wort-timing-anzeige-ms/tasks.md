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
- [x] Commit `0aad9c8` + Push auf main
- [x] CI-Pipeline **5282**: `build-webapp`/`test-frontend`/`test-webapp`/`grep-gate`/`mirror-github` success (`mirror-ghcr` hängt, bekannt — Image ist in Harbor)
- [x] Deploy auf KI-Box (`/opt/container/polyschnack`), Digest `sha256:1803c8cb…`, Container recreated+started
- [x] **Live-Verifikation im ausgelieferten Bundle** (`/assets/index-CFHN3dTO.js`):
      `NE=48e3` (= MAX_TIMING_PPS 48000), `Hl=.05` (MIN_PPS), `wl=.02` (MIN_WORD_DURATION_S),
      `toFixed(3).padStart(6,"0")` (= fmtShortTimecode)
- [x] Smoke-Test im Browser: HTTP 200, React mounted, **0 Konsolenfehler**
- [ ] Sichtprüfung durch den Nutzer: Wortlänge zeigt Millisekunden; sehr kurzes Wort füllt ~30 % der Breite

## Geänderte Dateien

- `frontend/src/format.ts`
- `frontend/src/format.test.ts`
- `frontend/src/components/TimingEditor.tsx`
- `frontend/src/waveformTime.ts`
- `frontend/src/waveformTime.test.ts`
