# Change 082 — Heartbeat-Visualisierung + echte ETA aus Dateilänge

## Problem

1. **Heartbeat unsichtbar:** Das Backend tickt `last_heartbeat_at` alle 5 s
   (Change 047), die UI zeigt aber nur eine subtile Puls-Animation und die
   Stall-Warnung. Der User sieht nicht, DASS noch etwas passiert.
2. **Fake-ETA:** `etaFromRate`/`updateEta` (Change 011) schätzen die ETA aus
   der Fortschritts-Rate (%/s der Polls). In stillen Phasen (Diarization bei
   96 %) liefert das „~1s"-Werte oder alte Raten — genau die Fake-ETA, die
   der User ablehnt (aligner-live-progress.md, User-Prinzip: Progress nur
   echte Backend-Prozesse).
3. **Keine ETA aus Dateilänge:** `duration_s` liegt seit dem Upload vor
   (set_processing hält es bewusst für eine ETA), wird aber nie genutzt.

## Lösung

- **Heartbeat visualisieren:** Ampel-Punkt (grün < 8 s pulsierend,
  gelb 8–45 s, rot > 45 s), Live-Zähler „Herzschlag vor Xs" (tickt im
  Frontend sekündlich, springt bei jedem Poll zurück), aktiver Phasen-Chip
  zeigt „· läuft seit mm:ss" (sincePhase, Daten vorhanden).
- **Echte ETA:** Backend rechnet aus `duration_s × RTF` je Backend/Phase.
  RTF-Werte kommen aus dem Benchmark (22.08., RTX-3090-Messungen);
  Diarization/Overheads konservativ geschätzt. Keine ETA bei unbekanntem
  Backend (Anti-Fake-Regel). Anzeige als Bereich „noch ca. 4–7 min
  (geschätzt)". Die Rate-ETA (`etaFromRate`) wird entfernt.

## Nicht-Ziele

- Kein selbstlernendes RTF (gleitender Mittelwert aus abgeschlossenen
  Jobs) in diesem Change — Phase 2, im Design skizziert.
- Keine Änderung am Progress-Balken selbst (bleibt echter Backend-pct).
