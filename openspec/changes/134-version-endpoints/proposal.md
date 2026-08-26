# Change 134: Versions-Endpunkte für alle Stack-Container

## Problem

Nach einem Deploy gibt es keinen Weg, per API zu prüfen, welche Commit-SHA
(e.g. `4a41b46e`) ein Container tatsächlich laufen lässt. Der `/health`-Endpunkt
der Webapp liefert nur `status`/`db`/`asr_url`. Der User muss Features
abklopfen („zeigt der aligner_diag das cstr-Modell?") oder Docker-Login auf
Harbor/ghcr machen — beides umständlich und fehleranfällig.

## Ziel

Jeder Container des Stacks macht seine **Git-Commit-SHA** (CI_COMMIT_SHORT_SHA)
maschinenlesbar verfügbar:

1. **Python-Services** (webapp, aligner, sep, approach-a, whisper): echter
   HTTP-Endpunkt `GET /api/version` bzw. `GET /version` → `{"service", "commit",
   "image_tag"}`. Commit kommt aus der Build-Env `GIT_SHA`.
2. **C++-CrispASR-Server** (diar + 7 ASR-Backends): fester Server ohne
   Versions-Endpunkt → Commit als **Docker-Label**
   (`org.opencontainers.image.revision`) + `ENV GIT_SHA` im Image; abrufbar
   via `docker inspect --format '{{index .Config.Labels ...}}'`.
3. **Build-Pipeline**: `scripts/ci_smart_build.sh` übergibt
   `--build-arg GIT_SHA=${CI_COMMIT_SHORT_SHA}` — eine Stelle für alle 14
   Images. Lokale Builds ohne CI bekommen `GIT_SHA=dev`.

## Nicht-Ziel

- Kein neuer Aggregations-Endpunkt in der Webapp, der alle Backend-Versionen
  sammelt (kann später als eigener Change kommen).
- Kein CrispASR-Fork-Patch für einen `/version`-Endpunkt im C++-Server.

## Kontext

- Builds laufen zentral über `scripts/ci_smart_build.sh` (alle Jobs in
  `.gitlab-ci.yml` rufen es mit Registry/Image/Context auf).
- Python-Services: `webapp/` (FastAPI), `aligner-service/aligner_server.py`
  (stdlib), `sep-service/sep_server.py` (stdlib), `approach-a/` (FastAPI),
  `whisper-service/server.py` (FastAPI).
- C++-Backends: `crispr-diar`, `crispr-pk-cpp`, `crispr-qwen3`, `crispr-ark`,
  `crispr-moonshine-de`, `crispr-canary`, `crispr-voxtral`,
  `crispr-whisper` — alle `crispasr --server` (nur `/health`).
