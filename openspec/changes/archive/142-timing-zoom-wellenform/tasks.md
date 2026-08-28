# Change 142 — Tasks (Timing-Zoom Wellenform)

## 1. Frontend

- [x] `WaveformPlayer.tsx`: Timing-Zoom aktiv → `setOptions({barWidth: 0,
      barGap: 0, barRadius: 0})` vor `zoom()`; Verlassen → zurück auf
      `{barWidth: 2, barGap: 1, barRadius: 2}`; try/catch-gesichert

## 2. Verifikation

- [x] tsc clean, 378 Vitest grün, build OK

## 3. OpenSpec + Commit

- [x] CLI-Validierung, Archivierung
- [x] Commit, Push, CI-Watch, melden
