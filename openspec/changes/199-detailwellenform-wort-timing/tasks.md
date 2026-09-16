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
- [x] Commit + Push (`fecc067`, `3994da0`) — laufende Pipelines vorher
      abgebrochen (`/opt/data/scripts/ci_cancel_running.sh`)
- [ ] CI abwarten (Pipeline #5293)
- [ ] Deployen (`/opt/data/scripts/ps_199_deploy.sh`), Bundle-Hash gegen den
      lokalen Build prüfen, Migrationsspalten kontrollieren
- [ ] **Live-Messung an `b68d6e39…`** (`/opt/data/scripts/ps_199_live_messung.sh`):
      - Sidecar-Größen (hi/res) auf der Platte
      - Übertragung pro Detailfenster (Ziel ~1–2 KB statt 6 MB)
      - Balken pro 1000 px im Wort-Zoom (Ziel ≥ 300 statt 6)
      - **kein ffmpeg-Lauf im Serverlog bei einem Zoom-Wechsel**
      - Enhance-Blende im Browser: Übergang, Dauer, und dass sie bei
        `prefers-reduced-motion` ausbleibt
- [ ] Nachlauf über den Bestand beobachten (93 Aufnahmen, ~10 min) und den
      ersten echten Sidecar gegen die Dauer prüfen

## Messungen

- **Korpus (16.09.):** 93 Aufnahmen, 27,9 h Audio. Sidecars zusammen 0,15 GB
  (hi 0,10 + res 0,05) = **3,3 % der 4,52 GB Audiodaten**. Nachlauf 10 min für
  den gesamten Bestand bei 21 s je Stunde Audio. 1,9 TB frei — das im Proposal
  als Risiko notierte Speicherwachstum ist damit quantifiziert und unkritisch.
- Browser-Breitengrenze: 2^25 = 33.554.428 px (gemessen)
- Voll-Decode Ausgangszustand: 3,23 s für 262 min (bei jeder Anfrage)

## Bewusst nicht in diesem Change

Kein Eingriff in WaveSurfer-Interna, kein Detail während des Abspielens, keine
eigene Zeitachsen-Übersetzung, kein AbortController für das residente Envelope
(Begründungen im Proposal).
