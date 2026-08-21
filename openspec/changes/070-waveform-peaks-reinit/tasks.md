# Change 070 — Tasks

## 1. Fix

- [x] WaveformPlayer: Init-Effect-Dependencies `[audioUrl, backend,
      inView, peaks, durationHint]`
- [x] Cleanup: timerRef (loadTimeout) clearen beim Re-Init/Unmount

## 2. Tests

- [x] WaveformPlayer.peaks.test.tsx (4): ohne Peaks → undefined;
      mit Peaks → [peaks]+duration; nachträglich → Re-Init; destroy
- [x] Lazyload-Tests weiterhin grün (2 Dateien, 7 Tests)
- [x] Frontend 240/240 · tsc 0

## 3. Abschluss

- [ ] Commit + Push + CI
