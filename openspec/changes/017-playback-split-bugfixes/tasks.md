# Change 017 — Tasks

## Phase 1: Doku + Validierung

- [x] 1.1 proposal.md: 6 User-Befunde + Root Causes + Lösungsansatz
      (Commits referenziert).
- [x] 1.2 specs/transcription/spec.md: Requirement-Deltas (ADDED) für
      Playback-Terminierung, Preview-Pflicht, Karaoke-Eindeutigkeit,
      iOS-Mikro-Release, Split-Markierung/Icon, Markieren≠Play.
- [x] 1.3 `openspec validate 017-playback-split-bugfixes` grün.

## Phase 2: Umsetzung (Commits, bereits gemergt)

- [x] 2.1 `491020f` — iOS: Mikrofon-Release nach Aufnahme (kein Prewarm
      auf WebKit, Session-Restore; Helfer + Tests).
- [x] 2.2 `9a208e2` — Playback: Decode-Polling statt Doppel-Fetch,
      90s-Timeout sichtbar; deterministische Preview-URL + synchrones
      Sidecar (Backend); Karaoke: kein Wort-Kleben, Markierung nur im
      aktiven Segment.
- [x] 2.3 `1f168ee` — Split-Desktop: Markierung bleibt bis Symbol-Klick,
      selectionchange-Guard, Symbol-Clamp.
- [x] 2.4 `575e3d8` — Symbol mittig zur Auswahl + 26px-Kreis/18px-Icon.
- [x] 2.5 `2f7fd98` — Markieren ≠ Play (onClick-Guard, Touch-Tap ohne
      Split-Anker).

## Phase 3: Qualität

- [x] 3.1 `npx tsc --noEmit` grün; `npx vitest run` grün (167/167).
- [x] 3.2 CI-Pipelines #4093/#4094/#4096 success (#4097/#4098 zum
      Zeitpunkt der Doku noch running).
- [ ] 3.3 Deploy beim User + Browser-Verifikation (Firefox: Markieren ohne
      Play, Icon mittig/sichtbar; iOS: Mikro-Indikator weg; Playback lädt
      nur die Preview).
