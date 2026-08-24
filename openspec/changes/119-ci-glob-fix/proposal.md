# Change 119 — CI-Fix: changes-Globs (**/*) + mirror-ghcr SHA-Guard

## Problem

Nach Change 117 (CI changes-Filter) zwei Fehler:

1. **changes-Globs matchen nicht:** GitLab-Doku verlangt für „Verzeichnis +
   alle Unterverzeichnisse" das Muster `path/to/directory/**/*` — unser
   `webapp/frontend/**` (ohne `/*`) matchte die tief verschachtelten
   Dateien nicht. Folge: Push-Pipeline 4467 für ee1131d (webapp-Änderung)
   erstellte nur die Mirror-Jobs — test-frontend/build-webapp liefen nie,
   das neue Frontend wurde nicht gebaut. (Manueller Trigger 4468 baute
   alle 20 Jobs, weil `changes` ohne Push-Event immer true ist.)
2. **mirror-ghcr schlägt fehl:** Das Script taggt/pusht für jedes der 13
   Images `:${CI_COMMIT_SHORT_SHA}`. Wurde ein Image in dieser Pipeline
   nicht gebaut (changes-Filter), existiert das SHA-Tag nicht →
   `docker tag` bricht → Pipeline failed (4465/4466/4467).

## Lösung

- `.gitlab-ci.yml`: alle changes-Muster `xyz/**` → `xyz/**/*`
  (docs, approach-a, webapp, webapp/frontend, alle build-Kontexte;
  compose*.yml bleibt).
- `.gitlab-ci.yml` mirror-ghcr: SHA-Tag nur taggen/pushen, wenn
  `docker manifest inspect ${src}:${SHA}` existiert; sonst überspringen
  mit Hinweis. `:latest` wird weiter immer gespiegelt.
- `OptionsPanel.tsx`: useEffect-Deps um `backends.length` +
  `streamingSupported` ergänzt (Tab-Auto-Switch reagiert auch auf
  Backend-Nachladung) — gleichzeitig echter webapp/frontend-Change,
  um die Glob-Korrektur im selben Push zu verifizieren.

## Tests / Verifikation

- tsc + npm test (312) lokal
- Push: Pipeline muss test-frontend + test-webapp + build-webapp +
  Mirror enthalten (KEINE ASR-Builds) — beweist Glob-Fix
- mirror-ghcr muss SUCCESS sein (SHA-Guard)
