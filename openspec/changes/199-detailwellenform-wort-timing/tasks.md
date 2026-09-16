# Change 199 — Aufgaben

## Backend

- [ ] `app/peaks.py`: `peaks_from_s16le` um ein zweites, feineres Envelope
      erweitern (ein Dekodierlauf → Hi-Level 1000 Bins/s füllen; residentes
      Level und 2000er-JSON daraus per `np.maximum.reduceat` ableiten —
      kein zusätzlicher ffmpeg-Lauf)
- [ ] `app/peaks.py`: Sidecar-Pfade + `write_peaks_sidecars(path, ...)`
      (idempotent: existiert die Datei mit plausibler Größe, nicht neu
      rechnen), Konstanten `HI_BPS = 1000`, `RESIDENT_BIN_BUDGET = 2_097_152`
- [ ] `app/models.py`: Spalten `peaks_hi_path`, `peaks_res_path`
      (+ Größen für die Übersicht, analog `preview_path` / `preview_size_bytes`)
- [ ] `app/routers/recordings.py`: Sidecar-Erzeugung in
      `_compute_peaks_background` einhängen (derselbe Dekodierlauf wie die
      Peaks), `.gitignore`-/Backfill-Pfad prüfen
- [ ] `app/routers/recordings.py`: `GET /recordings/{rid}/peaks.bin`
      (`level=res|hi`) als `FileResponse` mit Range-Unterstützung,
      Zugriffsprüfung wie bei `/peaks`
- [ ] `_backfill_peaks_batch` für Bestandsaufnahmen erweitern (Batch-Grenze
      bleibt, damit der Nachlauf nicht in die Request-Zeit fällt)
- [ ] Tests: Sidecar-Länge == `round(Dauer × 1000)`; Ableitung des 2000er-
      Envelopes aus dem Hi-Level reproduziert die Werte; `bins/s`-Formel;
      Range-Verhalten des Endpunkts

## Frontend

- [ ] `api.ts`: `fetchPeaksBinary(rid, level)` (ArrayBuffer) statt
      `fetchPeaks(rid, length)` für die Timeline; uint8 → float in [0,1]
      beim Dekodieren
- [ ] `WaveformPlayer.tsx`: residentes Envelope über `?level=res` laden und
      per `setPeaks` übergeben (ersetzt den JSON-Pfad); Ladezustand sichtbar,
      Fehler nicht still
- [ ] `waveformTime.ts`: `residentBinsPerSecond(duration)` nach dem Budget,
      `effectiveMaxPps(duration)` = `min(MAX_TIMING_PPS, 2^25 / duration)`
- [ ] `waveformTime.test.ts`: Budget-Invariante `BUDGET × Breite / 2^25` ist
      unabhängig von der Dauer; `effectiveMaxPps` für 10 min / 1 h / 262 min
- [ ] Change-197-Invariante korrigieren: „30-%-Fenster" gilt nur, solange
      `duration ≤ 2^25 / (0.3 × Breite / MIN_WORD_DURATION_S)` — sonst als
      bekannte Grenze dokumentiert statt als Zusicherung
- [ ] `WaveformPlayer.tsx`: Detail-Canvas (Overlay) — im Timing-Modus und
      pausiert das sichtbare Fenster ± 50 % als `Range`-Anfrage auf
      `?level=hi`, 1 Bin pro Pixel zeichnen, an derselben Zeitachse wie WS
- [ ] Detail-Layer beim Abspielen ausblenden (keine Anfragen im Play-Zustand)
- [ ] Enhance-Blende: Zustandsmaschine grob → fein, ~320 ms, zwei Phasen
      (Rauschen 0–120 ms, auflösen 120–320 ms), `prefers-reduced-motion`
      überspringt
- [ ] Tests: Detailfenster-Berechnung (Byte-Offsets im Sidecar), Layer-
      Sichtbarkeit abhängig von Play/Pause, Blenden-Zustandsmaschine und
      Reduced-Motion-Pfad

## Abschluss

- [ ] `npm run build` (exit 0) und volle Testsuite grün
- [ ] Commit + Push (vorher laufende Pipelines abbrechen —
      `/opt/data/scripts/ci_cancel_running.sh`)
- [ ] CI abwarten, deployen (`/opt/container/polyschnack`, `polyschnack-manage.sh`),
      Bundle-Hash gegen den lokalen Build prüfen
- [ ] **Live-Messung an `b68d6e39…`:**
      - Sidecar-Größen (hi/res) auf der Platte
      - Übertragung pro Detailfenster (Ziel ~1–2 KB statt 6 MB)
      - Balken pro 1000 px im Wort-Zoom (Ziel ≥ 300 statt 6)
      - **kein ffmpeg-Lauf im Serverlog bei einem Zoom-Wechsel**
      - Enhance-Blende im Browser: Übergang, Dauer, und dass sie bei
        `prefers-reduced-motion` ausbleibt
