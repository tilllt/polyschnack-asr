# Change 072 — Tasks

## 1. Fix

- [x] `WaveformPlayer.tsx`: `outerRef` auf äußerem Wrapper
- [x] Observer beobachtet `outerRef` statt `containerRef` (hidden bis ready)
- [x] Root-Cause-Kommentar im Code

## 2. Tests

- [x] Fake-IntersectionObserver recordet beobachtete Elemente
- [x] Regression: beobachtetes Element ≠ hidden Container (sichtbarer Vorfahre)
- [x] Regression: Init startet trotz hidden Container (070-Fix greift)
- [x] `WaveformPlayer.peaks.test.tsx` 6/6 grün

## 3. Gates

- [x] Frontend-Vollsuite (`npm test`) grün — 245/245
- [x] `tsc --noEmit` exit 0
- [x] `npm run build` ok

## 4. Abschluss

- [ ] Commit + Push
- [ ] CI grün
- [ ] Nach Deploy: Live-Verifikation (Waveforms laden auf langsamer Verbindung)
