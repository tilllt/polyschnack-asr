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
- [x] Commit + Push (`c64b839`)
- [x] CI-Pipeline **5287**: `test-frontend`/`test-webapp`/`grep-gate`/`build-webapp`/`mirror-github` success
- [x] Deploy auf KI-Box — Container recreated+started
- [x] Bundle-Gegenprobe live: `index-DFEGFFCC.js` (identisch zum lokalen Build),
      `"WebAudio"&&typeof Worker<"u"&&!!` + `RE=1800` im Main-Bundle,
      Invariante in `fetch.worker-BjMUf77s.js`
- [x] **E2E Mechanismus** (Browser, anonym, gemeldeter Share):
      `<audio src=/api/recordings/b68d6e39…/audio/preview>` →
      `duration_s = 15718` (262 min, korrekt), `readyState = 4`,
      **kein `blob:`**, `initiatorType = "audio"`,
      **transferSize 300 + 91.444 B ≈ 91 KB statt 46,9 MB → 512× weniger**
- [x] Range-Unterstützung serverseitig belegt: `206` mit
      `content-range: bytes 0-1023/46949384`, Seek aus der Mitte, Multipart-Ranges
- [x] Peaks-Quelle: 2000 Werte in 38 KB / 2,0 s (Welle hängt nicht mehr am Download)
- [ ] **Offen — Sichtprüfung im eingeloggten Player.** Die anonyme Share-Ansicht
      rendert bewusst keinen Player (Disclaimer: „Jeder mit dem Link kann die
      Transkription ansehen"), der Code-Pfad ist damit nicht anonym E2E prüfbar.
      WaveSurfer selbst (Welle über die volle Länge, Zoom, Timing-Tab) muss am
      eingeloggten Konto gegengeprüft werden.

## Nicht reproduzierbar in dieser Umgebung

Der ursprüngliche Auslöser — eine **langsame Leitung** — ließ sich hier nicht
herstellen (Rechenzentrums-Anbindung). Verifiziert ist deshalb: die
Empfindlichkeit gegen abgebrochene Downloads (Invariante, Tests) und der
Mechanismus, der den Volldownload ersetzt (Messung oben). Nicht gemessen ist
der ursprüngliche Nutzerfall „nach einer Weile korrupt" unter Drosselung.

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
