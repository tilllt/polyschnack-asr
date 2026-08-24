# Change 117 — CI: Nur betroffene Jobs bauen (changes-Filter)

## Problem

Jeder Push auf `main` erzeugt die komplette Pipeline: alle 15 Build-Jobs
(qwen3, ark, diar, aligner, sep, cpp, moonshine-de, canary, voxtral,
whisper-crisp, whisper, asr, webapp + 2 Mirror) plus alle Tests — egal,
welche Dateien geändert wurden. Ursache: jeder Job hat nur `only: - main`
ohne `changes:`-Filter.

`scripts/ci_smart_build.sh` schützt nur vor Re-Runs **derselben** Pipeline
(SHA-Guard: `docker manifest inspect ${SRC}:${SHA}`). Bei jedem neuen Commit
ist der SHA neu → alle Container werden wirklich neu gebaut, auch wenn ihr
Quellverzeichnis kein Byte verändert hat (z. B. Frontend-only-Push → 10 ASR-
Container-Builds à 30–90 min).

## Lösung

- Jeder Job bekommt `rules:` mit `changes:` auf sein Quellverzeichnis:
  - `build-diar` → `diar-service/**`, `build-qwen3` → `qwen3-asr-cpp/**`,
    `build-sep` → `sep-service/**`, `build-aligner` → `aligner-service/**`,
    `build-cpp` → `pk-asr-cpp/**`, `build-moonshine-de` → `moonshine-de-cpp/**`,
    `build-canary` → `canary-asr-cpp/**`, `build-voxtral` → `voxtral-crisp/**`,
    `build-whisper-crisp` → `whisper-crisp/**`, `build-whisper` → `whisper-service/**`,
    `build-ark` → `ark-asr-cpp/**`, `build-asr` → `approach-a/**`,
    `build-webapp` → `webapp/**`
  - `test-core` → `approach-a/**`, `test-webapp` → `webapp/**`,
    `test-frontend` → `webapp/frontend/**`, `compose-validate` → `compose*.yml`,
    `pages` → `docs/**`
- Mirror-Jobs (`mirror-github`, `mirror-ghcr`) laufen weiter bei jedem
  main-Push (kein changes-Filter), ihre `needs`-Listen werden auf
  `optional: true` gestellt → sie warten nur auf Jobs, die tatsächlich
  existieren; bei geskippten Jobs laufen sie trotzdem (GitHub-/GHCR-Stand
  bleibt synchron). Bei failed Jobs laufen sie weiterhin nicht (Pipeline
  muss grün sein).
- Alle `needs:` auf Test-Jobs werden `optional: true` (sonst bricht ein
  Build-Job, wenn sein Test-Job wegen fehlender Änderungen übersprungen
  wurde — z. B. `build-qwen3` bei nur `qwen3-asr-cpp/**`-Änderung).

## Auswirkung

Frontend-only-Push: nur `test-frontend` + `test-webapp` + `build-webapp`
(+ Mirror) laufen; die ASR-Container-Builds entfallen. Push ohne relevante
Änderungen (z. B. nur `.gitlab-ci.yml`): Pipeline wird `skipped`.

## Tests / Verifikation

- YAML-Syntax lokal (pyyaml) nach der Transformation
- Push → Pipeline-Status prüfen: bei reinem CI-Change muss die Pipeline
  `skipped` sein (beweist: Filter greift)
- Nächster echter Code-Push: nur betroffene Jobs in der Job-Liste
