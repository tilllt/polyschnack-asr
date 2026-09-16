# Change 198 — Implementation

## Tasks

- [x] Ursachenkette belegt (98-min-Share, 46,9 MB Preview, 6,3 Mbit/s Timeout-Grenze)
- [x] Truncation empirisch nachgewiesen: `decodeAudioData` im echten Browser →
      3 MB von 47 MB ergibt `decode_fehler: null`, Dauer 1021 s statt 5868 s
- [x] Invariante in `fetch.worker.ts`: `received !== total` → Fehler statt
      stiller Korruption; nur bei `content-encoding: identity` (gzip-Fehlalarm vermieden)
- [x] `useWorker`-Konstante in `WaveformPlayer.tsx`: Worker nur im WebAudio-Modus
- [x] Fortschritts-Handler (`ws.on("loading")`) an dieselbe Konstante gekoppelt
      — sonst wäre die Ladeanzeige bei MediaElement bei 0 % stehen geblieben
- [x] `export {}` im Worker (Modul-Marker, sonst nicht importierbar im Test)
- [x] Tests: `fetch.worker.test.ts` (3 Fälle: vollständig / abgeschnitten / gzip)
- [x] Tests: `WaveformPlayer.change198.test.tsx` (4 Fälle: MediaElement ohne Worker,
      WebAudio mit Worker, Grenze 1800 s, ohne Worker verfügbar)
- [x] Tests: **417 grün** (35 Dateien, +7)
- [x] `npm run build`: exit 0 — Bundle `index-DFEGFFCC.js`, Worker-Chunk `fetch.worker-BjMUf77s.js`
- [x] Bundle-Gegenprobe: Invariante im Worker-Chunk, `RE=1800` +
      `"WebAudio"&&typeof Worker<"u"&&!!t` im Main-Bundle
- [ ] Commit + Push
- [ ] CI-Pipeline abwarten
- [ ] Deploy auf KI-Box
- [ ] **E2E am gemeldeten Share** (`/r/b68d6e39…`, anonym): Wellenform über die
      volle Länge (~98 min), kein `blob:`-Audio, Range-Requests im Netz-Log

## Geänderte Dateien

- `frontend/src/workers/fetch.worker.ts` (Invariante + Modul-Marker)
- `frontend/src/components/WaveformPlayer.tsx` (`useWorker`, Fortschritts-Handler)
- `frontend/src/workers/fetch.worker.test.ts` (neu)
- `frontend/src/components/WaveformPlayer.change198.test.tsx` (neu)

## Bewusst NICHT in diesem Change

- **AbortController für den Worker-Fetch.** Der 47-MB-Download läuft weiter,
  wenn der Player unmountet oder der Timeout feuert. Ressourcen-Verschwendung,
  aber kein Korruptionspfad mehr (die Invariante fängt den Abbruch jetzt ab).
  Eigener Change — `workerFetch` müsste dafür einen Handle mit `abort()`
  zurückgeben (postMessage kann keinen AbortSignal übertragen).
