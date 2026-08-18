# Change 019 — Karaoke-Sync: Polling auch bei Tab-Wechsel fortsetzen

## Problem

Die Karaoke-Wort-Hervorhebung folgt der Playback-Position über einen
rAF-Sync-Loop (`WaveformPlayer`): solange `ws.isPlaying()`, liest jeder
Animation-Frame `ws.getCurrentTime()` und pusht die Zeit nach oben
(`onTimeUpdate` → `currentTime` → `activeWordIndex`). Das ist eine einzige
Uhr — zwischen Anzeige und Playback-Position kann kein Drift entstehen.

**Lücke:** Sobald der Tab in den Hintergrund geht (App-Wechsel auf dem
Handy, Tab-Wechsel im Browser), feuert `requestAnimationFrame` nicht mehr
(gedrosselt/gestoppt). Das WebAudio-Playback läuft aber weiter. Folge: Die
Karaoke-Anzeige, der Autoscroll und die Zeit-Anzeige **frieren ein**, während
das Audio weiterläuft. Kommt der User zurück, springt die Anzeige schlagartig
nach — das fühlt sich wie ein wachsender Drift an („je länger es läuft, desto
mehr weicht das Playback vom Karaoke-Timing ab"). Es gibt keinen
`visibilitychange`-Handler und kein Fallback-Polling für den Hidden-Zustand.

## Lösung

Das Polling bleibt die einzige Zeitquelle (kein zweiter Zähler, kein
Drift-Monitor). Es wird nur gegen die Tab-Drosselung abgesichert:

- **Hidden:** Beim `visibilitychange` auf `hidden` wird der rAF-Loop gestoppt
  und ein `setInterval`-Fallback (500 ms) gestartet, der weiterhin
  `ws.getCurrentTime()` pollt (Intervall-Timer feuern im Hidden-Tab weiter,
  ~1×/s). Die Anzeige bleibt damit grob synchron statt einzufrieren.
- **Visible:** Beim Zurückkehren wird der Interval gestoppt, der rAF-Loop neu
  gestartet und **sofort** einmal synchronisiert — kein akkumulierter Sprung
  mehr, die Anzeige steht direkt wieder auf der echten Position.
- Cleanup im Unmount (beide Timer).

## Betroffene Dateien

- `frontend/src/components/WaveformPlayer.tsx` (Visibility-Handler + Fallback-Polling)
- `frontend/src/components/WaveformPlayer.test.tsx` (Regressionstest, falls vorhanden/erweiterbar)
