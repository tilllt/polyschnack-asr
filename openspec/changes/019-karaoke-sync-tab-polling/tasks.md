# Tasks — Change 019 (Karaoke-Sync bei Tab-Wechsel)

- [x] `WaveformPlayer.tsx`: `visibilitychange`-Handler (hidden → Interval-Fallback 500 ms, visible → sofortiger Sync + rAF-Neustart), Unmount-Cleanup
- [ ] Regressionstest: kein Unit-Test möglich — es gibt kein Test-Harness für den WaveSurfer-Mock; Absicherung über tsc + vitest 175/175, Live-Verifikation nach Deploy (Handy: App-Wechsel während Playback)
- [x] `npx tsc --noEmit` und `npx vitest run` grün (175/175)
- [ ] Commit + Push, CI-Status prüfen
