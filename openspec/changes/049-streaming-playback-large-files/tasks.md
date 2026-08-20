# Tasks — Change 049: Streaming-Playback (MediaElement) für sehr lange Aufnahmen

## Task 1: Backend-Wahl

- [x] `resolveBackend(durationHint)` exportiert: > 7200 s → "MediaElement",
      sonst "WebAudio" (LARGE_FILE_THRESHOLD_S = 7200)
- [x] WaveSurfer.create mit dynamischem backend

## Task 2: canPlay-Freigabe backend-abhängig

- [x] MediaElement: Polling auf `readyState >= 3` (HAVE_FUTURE_DATA) des
      internen `<audio>`-Elements
- [x] WebAudio: unverändert (getDecodedData-Polling)

## Task 3: Timeouts

- [x] MediaElement: 120 s Load-Timeout (Server-Preview-ffmpeg kann beim
      ersten Zugriff Minuten dauern); Fehlerpfad bleibt ws.on("error")
- [x] WebAudio: unverändert (10 s mit Peaks / 60 s Decode-Pfad)
- [x] canPlay-Timeout (90 s) bleibt für beide

## Task 4: Tests

- [x] Unit: resolveBackend (kurz → WebAudio, 4h52min → MediaElement,
      Grenze 7200 s bleibt WebAudio) — 3 neue Tests
- [x] 191/191 Frontend-Tests grün, tsc sauber, npm run build ok

## Task 5: Commit

- [ ] Commit + Push + CI prüfen
- [ ] Hinweis an User: nach Deploy auf Box testen (4h52min-Datei auf Handy)
