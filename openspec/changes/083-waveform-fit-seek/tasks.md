# Tasks — Change 083

- [ ] T1: `frontend/src/waveformTime.ts` — MIN_PPS, fitPps, timeFromClick
- [ ] T2: WaveformPlayer: minPxPerSec, ppsRef, doZoom mit idx0=fit,
      ready → doZoom(ws, 0)
- [ ] T3: Klick-Handler: timeFromClick mit ws.getScroll()
- [ ] T4: Zoom-UI-Label „fit" bei idx 0
- [ ] T5: Tests (waveformTime.test.ts) + tsc + vitest + build
- [ ] T6: Vollsuite, Commit, Push, CI-Watch
- [ ] T7: Flaky-Fix test_install_via_git_uses_sha_file — deterministische
      ZIP-Fixtures (fixe date_time in _make_set_zip); CI #4325 schlug hier
      fehl (2-s-Zeitstempel-Granularität), nicht wegen 083
