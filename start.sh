#!/usr/bin/env bash
# ==============================================================
# PolySchnack — Stack starten (Core + optionale Backends provisionieren)
# --------------------------------------------------------------
#   ./start.sh
#
# - Bringt den Kern-Stack hoch (docker-proxy, ps-pk-onnx, crispr-diar,
#   ps-webapp) — mit GPU-Overlay, wenn die NVIDIA-Container-Runtime
#   verfügbar ist, sonst CPU-only (hybrid).
# - Provisioniert ALLE optionalen Backends mit --no-start: Container
#   werden angelegt, gestartet wird on demand über die Admin-GUI.
# - Bindet compose.oidc.yml ein, sobald echte Credentials hinterlegt
#   sind (Dummy-Werte werden erkannt und übersprungen).
#
# Idempotent: mehrfaches Ausführen ist unkritisch.
# ==============================================================
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.backends.yml)
# compose.backends.yml ist IMMER Teil des Projekts: die Overlays
# (compose.gpu.yml) referenzieren Backend-Services, die sonst ohne
# image/build existieren -> "invalid compose project". Ohne aktivierte
# Profile starten/erstellen die Backends beim up -d trotzdem NICHT.

# --- GPU-Overlay: nur wenn die NVIDIA-Container-Runtime existiert -------
if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi '"nvidia"'; then
    COMPOSE+=(-f compose.gpu.yml)
    echo "-> GPU-Overlay aktiv (NVIDIA-Runtime gefunden)"
else
    echo "-> Keine NVIDIA-Runtime - Stack startet CPU-only"
fi

# --- OIDC-Overlay: nur mit echten Credentials ---------------------------
if [ -f compose.oidc.yml ] && ! grep -qE 'dummy|auth\.example\.com|example\.com' compose.oidc.yml; then
    COMPOSE+=(-f compose.oidc.yml)
    echo "-> OIDC-Overlay aktiv (echte Credentials gefunden)"
elif [ -f compose.oidc.yml ]; then
    echo "! compose.oidc.yml enthaelt Dummy-Werte - OIDC uebersprungen"
fi

echo "-> Starte Kern-Stack ..."
"${COMPOSE[@]}" up -d

echo "-> Provisioniere optionale Backends (--no-start, GUI startet on demand) ..."
"${COMPOSE[@]}" \
    --profile crispr-pk-cpp --profile crispr-qwen3 --profile crispr-ark \
    --profile crispr-moonshine-de --profile crispr-canary \
    up -d --no-start

echo
echo "Fertig. Status:"
"${COMPOSE[@]}" ps
