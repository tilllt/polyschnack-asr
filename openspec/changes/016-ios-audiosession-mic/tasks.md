# Change 016 — Tasks

## Phase 1: Spec + Helfer

- [x] 1.1 `openspec validate 016-ios-audiosession-mic` grün.
- [x] 1.2 `UploadZone.tsx`: Helfer `ensureAudioSessionForRecording()`
      (Cast über `navigator.audioSession`, nur setzen wenn ≠
      `play-and-record`).

## Phase 2: Einbau in Record-Pfade

- [x] 2.1 `prewarmMic()`: Helfer VOR `getUserMedia`; catch → `console.warn`
      mit Fehlergrund (kein kompletter Silent-Fail).
- [x] 2.2 `startRecording()`: Helfer VOR `record.startRecording(...)`.
- [x] 2.3 Retry: catch im `try`-Block um `record.startRecording` —
      wenn Meldung „AudioSession category" enthält → Helfer + 1 Retry,
      sonst Fehler wie bisher werfen (Toast).

## Phase 3: Tests

- [x] 3.1 Vitest: Helfer setzt `audioSession.type` (mock navigator);
      setzt NICHT, wenn `audioSession` fehlt (Desktop-Browser).
- [x] 3.2 Vitest: Retry — erster `startRecording`-Aufruf wirft
      AudioSession-Fehler, zweiter Erfolg → genau 2 Calls.
- [x] 3.3 Vitest: Nicht-AudioSession-Fehler → kein Retry, Fehler
      propagiert.
- [x] 3.4 `npx tsc --noEmit` grün; `npx vitest run` grün.

## Phase 4: Abschluss

- [x] 4.1 Commit + Push; CI-Watchdog; Deploy-Hinweis (User deployt).
