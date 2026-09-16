# Change 199 — Aufgaben

## Backend

- [x] `app/peaks.py`: `envelope_from_s16le` — uint8-Max-Envelope in einem
      Streaming-Durchlauf. Die Quantisierung VOR dem Maximum ist verlustfrei
      (`max(floor(x)) == floor(max(x))`, floor ist monoton); `>> 7` bildet
      32767 auf 255 ab, der Sonderwert 32768 (aus `abs(-32768)`) wird auf 255
      gekappt statt auf 0 umzulaufen
- [x] `app/peaks.py`: `pool_envelope` (Max-Pooling nach unten),
      `envelope_to_floats` (2000er-JSON-Form aus dem Envelope), `read_envelope`,
      `_write_bytes_atomic` (erst `*.part`, dann umbenennen — ein abgebrochener
      Lauf darf keine halbe Datei hinterlassen, die die Längenprüfung dann für
      gültig hält), `_sidecar_plausible`, `write_peaks_sidecars`
- [x] `app/peaks.py`: Konstanten `HI_BPS = 1000`, `RESIDENT_BIN_BUDGET = 2_097_152`
- [x] `app/models.py`: `peaks_hi_path`, `peaks_hi_size_bytes`, `peaks_res_path`,
      `peaks_res_size_bytes` (Auto-Migration deckt die `recording`-Tabelle ab)
- [x] `app/routers/recordings.py`: `_ensure_peaks_sidecars` in
      `_compute_peaks_background` UND `_backfill_peaks_batch` — EIN Dekodierlauf
      füllt beide Ebenen; der 2000er-JSON-Vektor wird aus dem residenten
      Sidecar abgeleitet statt die Datei ein zweites Mal zu dekodieren
- [x] `app/routers/recordings.py`: `GET /recordings/{rid}/peaks.bin?level=res|hi`
      als `FileResponse` mit Range, Zugriff wie bei `/peaks`
- [x] `app/crud.py`: **Nachtrag nach der Umsetzung** — `list_recordings_missing_peaks`
      wählte nur nach fehlenden Peaks ODER fehlender Preview aus. Eine
      Bestandsaufnahme hat beides und bekam deshalb NIE ein Sidecar; der
      Nachlauf hätte den gesamten Altbestand nicht nachgezogen (die
      Live-Messung hätte nur „Basisauflösung" gezeigt). `peaks_res_path IS NULL`
      ist jetzt eine dritte Bedingung; der leere String ist der „versucht, nicht
      dekodierbar"-Marker (analog `[]` bei den Peaks, kein Endlos-Retry)
- [x] Tests: 29 in `tests/test_peaks_sidecar_199.py` — uint8-Quantisierung
      verlustfrei, Chunking == Einmalaufruf, Sonderwert-Kappung, Pooling,
      Budget-Invariante über die Dauer, idempotente und abgeschnittene
      Sidecars, nicht dekodierbare Datei, Endpunkt (Level, 404, Range/206/
      Überhang), Nachlauf-Auswahl (**rot/grün bewiesen**), Fehlschlag-Marker

## Frontend

- [x] `api.ts`: `fetchPeaksBinary(rid, level, range?)` (ArrayBuffer,
      `Range`-Header) + `envelopeToPeaks` (uint8 → float in [0,1])
- [x] `waveformTime.ts`: `residentBinsPerSecond`, `residentBinCount`,
      `hiBinCount`, `effectiveMaxPps`, `timingTargetReachable`,
      `windowBinRange`, `detailByteRange`
- [x] `waveformTime.test.ts`: Budget-Invariante (`BUDGET × Breite / 2^25` ist
      unabhängig von der Dauer), `effectiveMaxPps` für 10 min / 12 min /
      262 min, Detailfenster-Byteoffsets und Puffer-Abdeckung
- [x] Change-197-Invariante korrigiert: das 30-%-Zielfenster ist auf langen
      Dateien nicht haltbar (2^25 / Dauer deckelt; bei 262 min 2135 px/s statt
      48000) — über `timingTargetReachable` abfragbar statt als Zusicherung,
      die der Browser nicht einhalten kann
- [x] `detailWaveform.ts`: `enhancePhase`, `grainAmount`, `enhanceRunning`,
      `detailLayerVisible`, `windowColumns`, `columnRect`, `grainValue`,
      `prefersReducedMotion`
- [x] `DetailWaveformLayer.tsx`: Overlay-Canvas, lädt das sichtbare Fenster
      ± 50 % per Range, zeichnet eine Bin-Spalte pro Pixel, rahmt den Wechsel
      grob → fein mit ~320 ms Rausch-Blende
- [x] Detail-Ebene beim Abspielen aus (keine Anfragen im Play-Zustand)
- [x] `WaveformPlayer.tsx`: residentes Envelope per `setPeaks`,
      `effectiveMaxPps` im Timing-Zoom, Scroll-Verfolgung fürs sichtbare
      Fenster, sichtbarer Hinweis bei fehlendem Sidecar
- [x] `detailWaveform.test.ts`: Phasen, Reduced-Motion-Pfad, Sichtbarkeit,
      Spalten-Abbildung (Versatz, Maximum je Pixel, Streckung, Rand),
      Balkengeometrie

## Abschluss

- [x] `npm run build` exit 0 (`tsc && vite build`)
- [x] Volle Testsuite grün: Backend 1200, Frontend 449
- [x] Commit + Push (`fecc067`, `3994da0`, `3b14190`) — laufende Pipelines vorher
      abgebrochen (`/opt/data/scripts/ci_cancel_running.sh`)
- [x] CI grün (Pipeline #5293: mirror-ghcr, build-webapp, test-webapp, grep-gate)
- [x] Deployt auf Revision `3994da02`. Verifiziert: Health 200 von außen,
      ausgeliefertes Bundle `index-Cp8hfSDH.js` == lokaler Build (Hash-Gleichheit),
      alle vier Spalten migriert
- [x] **Live-Messung** (`/opt/data/scripts/ps_199_*`): Nachlauf über den Bestand
      gelaufen, 93/93 Aufnahmen mit Sidecar, 0 Fehlmarker, 0 unfertige
      `.part`-Dateien
- [x] Erster echtes Sidecar an der Referenzaufnahme: **hi 15.717.607 B**,
      res 2.097.152 B (exakt Budget)
- [ ] **Browser-Abnahme durch den Nutzer** (nicht messbar von außen):
      Deckungsgleiche Lage der Detail-Ebene über der WS-Welle, Blendeneffekt,
      und dass er bei `prefers-reduced-motion` ausbleibt
- [ ] Offen (nicht blockierend): echter HTTP-206 durch den Proxy. Mit `OIDC=1`
      braucht das eine angemeldete Sitzung; die Range-Logik ist
      applikationsseitig mit 206 und exakter Bytezahl getestet und das
      `FileResponse`-Range-Verhalten isoliert geprüft

## Messungen

- **Korpus vor der Umsetzung (16.09.):** 93 Aufnahmen, 27,9 h Audio. Prognose:
  Sidecars zusammen 0,15 GB = 3,3 % der 4,52 GB Audiodaten, Nachlauf 10 min.
- **Korpus nach dem Nachlauf (16.09., gemessen):** 93/93 Aufnahmen mit Sidecar,
  0 Fehlmarker, 0 unfertige `.part`-Dateien. **Echt auf der Platte: 106 Dateien,
  121,7 MB** — 93 hi-Dateien (95,7 MB) und nur 13 res-Dateien (26,0 MB), weil
  bei 80 Aufnahmen beide Ebenen auf dieselbe Datei zeigen. Die Prognose von
  0,15 GB kam aus der Summe beider Spalten und zählt diese 80 Dateien doppelt;
  real sind es 0,12 GB.
  Aufschlussreicher Vergleich: die 154 Preview-MP3s belegen **521,5 MB** — die
  Sidecars kosten also 23 % dessen, was die Vorschau-Audios ohnehin brauchen.
- Längenzusage bestätigt (Stichproben auf das Byte): 12,9 s → 12.931 B;
  24,2 s → 24.240 B; 2.169,6 s → 2.169.600 B mit res exakt 2.097.152 B.
- **Abweichung `duration_s` gegen die echte dekodierte Länge:** nur 31 von 93
  Aufnahmen stimmen exakt, die übrigen bis zu **1,83 %** (Median 0,019 %). Die
  Sidecar-Länge folgt der dekodierten Länge und ist korrekt — der gespeicherte
  `duration_s` (aus der Sonde) überschätzt sie, bei der 262-min-Zusammenführung
  um 8,07 s. **Für die Wellenform folgenlos**, weil die Achse im Player aus
  `ws.getDuration()` kommt (dekodierte Länge), nicht aus der API. Wäre sie aus
  der API, ergäbe sich eine Verschiebung von bis zu 1,8 % am Dateiende.
- Browser-Breitengrenze: 2^25 = 33.554.428 px (gemessen)
- Voll-Decode Ausgangszustand: 3,23 s für 262 min (bei jeder Anfrage)

## Bewusst nicht in diesem Change

Kein Eingriff in WaveSurfer-Interna, kein Detail während des Abspielens, keine
eigene Zeitachsen-Übersetzung, kein AbortController für das residente Envelope
(Begründungen im Proposal).
