#!/usr/bin/env bash
# Idempotenter CI-Build: baut nur, wenn das Image fuer diesen Commit-SHA noch
# nicht existiert. Bei Re-Run derselben Pipeline wird der Build uebersprungen
# und nur :latest neu getaggt — Artefakte bleiben erhalten.
#
# Nutzung (in .gitlab-ci.yml build-Jobs):
#   bash scripts/ci_smart_build.sh "<registry>" "<image>" "<build-context>" ["<dockerfile>"]
#
# Beispiel:
#   bash scripts/ci_smart_build.sh "${HARBOR_REGISTRY}/public" "polyschnack-asr-webapp" "webapp/"
#   bash scripts/ci_smart_build.sh "${HARBOR_REGISTRY}/public" "polyschnack-asr" "approach-a/" "approach-a/Dockerfile"
set -euo pipefail

BASE="$1"
IMG="$2"
CTX="$3"
DF="${4:-}"

SHA="${CI_COMMIT_SHORT_SHA:?CI_COMMIT_SHORT_SHA fehlt}"
SRC="${BASE}/${IMG}"

if docker manifest inspect "${SRC}:${SHA}" >/dev/null 2>&1; then
    echo "[ci-smart-build] ${IMG}:${SHA} existiert bereits — Build uebersprungen, :latest re-taggt"
    docker pull "${SRC}:${SHA}"
    docker tag "${SRC}:${SHA}" "${SRC}:latest"
    docker push "${SRC}:latest"
    exit 0
fi

echo "[ci-smart-build] baue ${IMG} (SHA ${SHA})"
# GIT_SHA als Build-Arg injizieren (Change 134): Container lesen die
# Commit-SHA aus ENV GIT_SHA bzw. org.opencontainers.image.revision-Label.
GIT_SHA="${CI_COMMIT_SHORT_SHA:-dev}"
if [ -n "$DF" ]; then
    docker build -f "$DF" --build-arg GIT_SHA="$GIT_SHA" \
        --label "org.opencontainers.image.revision=$GIT_SHA" \
        -t "${SRC}:latest" -t "${SRC}:${SHA}" "$CTX"
else
    docker build --build-arg GIT_SHA="$GIT_SHA" \
        --label "org.opencontainers.image.revision=$GIT_SHA" \
        -t "${SRC}:latest" -t "${SRC}:${SHA}" "$CTX"
fi
docker push "${SRC}:latest"
docker push "${SRC}:${SHA}"
echo "[ci-smart-build] fertig: ${SRC}:${SHA}"
