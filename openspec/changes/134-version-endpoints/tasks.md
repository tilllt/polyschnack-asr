# Change 134 — Tasks

## 1. Build-Pipeline: GIT_SHA in alle Images

- [x] `scripts/ci_smart_build.sh`: `--build-arg GIT_SHA=${CI_COMMIT_SHORT_SHA}`
      an `docker build` übergeben (sowohl mit als auch ohne `-f`-Pfad) +
      `--label org.opencontainers.image.revision`
- [x] Lokale Builds ohne CI: `GIT_SHA="${CI_COMMIT_SHORT_SHA:-dev}"`

## 2. Dockerfiles: ARG + ENV + Label

- [x] Alle 13 Dockerfiles (webapp, aligner, sep, diar, approach-a,
      whisper-service, pk-asr-cpp, qwen3-asr-cpp, ark-asr-cpp,
      moonshine-de-cpp, canary-asr-cpp, voxtral-crisp, whisper-crisp):
      `ARG GIT_SHA=dev` + `ENV GIT_SHA=${GIT_SHA}` + Label
      `org.opencontainers.image.revision=${GIT_SHA}` (nach der letzten FROM)

## 3. Python-Services: /version-Endpunkte

- [x] `webapp/app/main.py`: `GET /api/version` → `{"service": "webapp",
      "commit": GIT_SHA, "image_tag": GIT_SHA}`
- [x] `aligner-service/aligner_server.py`: `GET /version` im do_GET
      (+ openapi.json um /version ergänzt)
- [x] `sep-service/sep_server.py`: `GET /version` im do_GET
- [x] `approach-a/polyschnack_service/main.py`: `GET /api/version`
- [x] `whisper-service/server.py`: `GET /version`

## 4. Tests

- [x] Webapp: `tests/test_version_endpoint.py` (3 Tests: dev-Default,
      GIT_SHA aus Env, ohne Auth erreichbar) — 3 passed
- [x] Aligner: `tests/test_aligner_version.py` (3 Tests) — 24er-Suite OK
- [x] SEP: `tests/test_sep_version.py` (2 Tests) — OK
- [ ] Volle Backend-Suite grün (läuft: 1011+ Tests)

## 5. Doku

- [x] `docs/compose.md`: Abschnitt „Version prüfen (Change 134)" —
      Endpunkt-Tabelle (webapp/asr/aligner/sep) + `docker inspect` für
      C++-Backends

## 6. Commit, Push, CI

- [ ] Commit (Change 134), Push, CI-Watch bis success
- [ ] `polyschnack-manage.sh` Hinweis? (optional, nur falls einfach)
