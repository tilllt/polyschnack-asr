## ADDED Requirements

### Requirement: Karaoke-Polling läuft auch im Hintergrund-Tab weiter

- **Ablauf:** `WaveformPlayer` registriert einen `visibilitychange`-Handler.
  Beim Wechsel zu `hidden` wird der rAF-Sync-Loop gestoppt und ein
  `setInterval`-Fallback (500 ms) gestartet, der weiterhin `ws.getCurrentTime()`
  liest und über `onTimeUpdate` nach oben pusht. Beim Wechsel zu `visible`
  wird der Interval gestoppt, sofort einmal synchronisiert und der rAF-Loop
  neu gestartet, wenn `ws.isPlaying()`. Unmount räumt beide Timer auf.
- **Warum:** `requestAnimationFrame` feuert im Hidden-Tab nicht — die
  Karaoke-Anzeige fror ein, während WebAudio weiterlief; beim Zurückkehren
  sprang die Anzeige akkumuliert nach (Eindruck von Playback-Drift).
- **Architektur:** `frontend/src/components/WaveformPlayer.tsx`.
- **Zeitquelle unverändert:** Es gibt weiterhin NUR eine Uhr
  (`ws.getCurrentTime()`); kein zweiter Zähler, kein Resync-Vergleich.

#### Scenario: Handy-App-Wechsel während des Playbacks

- **Akteure:** User spielt eine Aufnahme ab, Karaoke läuft synchron.
- **Eingaben:** User wechselt in eine andere App (Tab → `hidden`).
- **Ergebnis:** Das Audio läuft weiter; die Anzeige folgt über den
  Intervall-Fallback grob (≈1–2×/s) statt einzufrieren. Beim Zurückkehren
  steht die Markierung sofort auf der korrekten Wort-Position, kein Sprung.

#### Scenario: Normales Playback im Vordergrund

- **Ablauf:** Unverändert — rAF-Loop (≈40 fps, 25-ms-Schwelle). Der
  Visibility-Handler greift nur bei Tab-Wechseln.
