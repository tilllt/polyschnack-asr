#!/usr/bin/env bash
# ==============================================================
# PolySchnack — Stack-Verwaltung (ersetzt start.sh)
# --------------------------------------------------------------
#   ./polyschnack-manage.sh [BEFEHL]   (ohne BEFEHL = start)
#
# Befehle:
#   pull        Zieht ALLE Images (Kern + optionale Backends, inkl. Profile)
#   start       Startet den Kern-Stack (docker-proxy, ps-pk-onnx, crispr-diar,
#               crispr-align, ps-webapp) und provisioniert die optionalen
#               Backends mit --no-start (Admin-GUI startet sie on demand).
#               GPU-Overlay automatisch, wenn die NVIDIA-Container-Runtime
#               verfügbar ist, sonst CPU-only (Hybrid-Binaries).
#               OIDC-Overlay, sobald echte Credentials in compose.oidc.yml
#               stehen (Dummy-Werte werden erkannt und übersprungen).
#   stop        Stoppt alle Container des Stacks (inkl. Backends).
#   restart     stop + start.
#   down        Entfernt die Container (Volumes bleiben erhalten).
#   status      Zeigt den Zustand aller Services (docker compose ps).
#   logs [SVC]  Folgt den Logs (alle Services oder nur SVC).
#   update      git pull + pull + start  (kompletter Deploy-Workflow).
#   help        Diese Hilfe.
#
# Idempotent: mehrfaches Ausführen ist unkritisch.
# ==============================================================
set -euo pipefail
cd "$(dirname "$0")"

# --- Projekt-Basis ----------------------------------------------------------
# compose.backends.yml ist IMMER Teil des Projekts: die Overlays
# (compose.gpu.yml) referenzieren Backend-Services, die sonst ohne
# image/build existieren -> "invalid compose project". Ohne aktivierte
# Profile starten/erstellen die Backends beim up -d trotzdem NICHT.
COMPOSE=(docker compose -f compose.yml -f compose.backends.yml)
PROFILES=(
    --profile crispr-pk-cpp
    --profile crispr-qwen3
    --profile crispr-ark
    --profile crispr-moonshine-de
    --profile crispr-canary
)

# --- Overlays (nur für Start-Kommandos relevant) ---------------------------
OVERLAYS=()
if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi '"nvidia"'; then
    OVERLAYS+=(-f compose.gpu.yml)
    echo "-> GPU-Overlay aktiv (NVIDIA-Runtime gefunden)"
else
    echo "-> Keine NVIDIA-Runtime - Stack startet CPU-only"
fi
if [ -f compose.oidc.yml ] && ! grep -qE 'dummy|auth\.example\.com|example\.com' compose.oidc.yml; then
    OVERLAYS+=(-f compose.oidc.yml)
    echo "-> OIDC-Overlay aktiv (echte Credentials gefunden)"
elif [ -f compose.oidc.yml ]; then
    echo "! compose.oidc.yml enthaelt Dummy-Werte - OIDC uebersprungen"
fi

cmd_start() {
    "${COMPOSE[@]}" "${OVERLAYS[@]}" up -d
    echo "-> Provisioniere optionale Backends (--no-start, GUI startet on demand) ..."
    "${COMPOSE[@]}" "${PROFILES[@]}" up -d --no-start
    echo
    echo "Fertig. Status:"
    "${COMPOSE[@]}" "${PROFILES[@]}" ps
}

usage() {
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

CMD="${1:-start}"
case "$CMD" in
    pull)
        echo "-> Ziehe ALLE Images (Kern + Backends) ..."
        "${COMPOSE[@]}" "${PROFILES[@]}" pull
        ;;
    start)
        cmd_start
        ;;
    stop)
        "${COMPOSE[@]}" "${PROFILES[@]}" stop
        ;;
    restart)
        "${COMPOSE[@]}" "${PROFILES[@]}" stop
        cmd_start
        ;;
    down)
        "${COMPOSE[@]}" "${PROFILES[@]}" down
        ;;
    status|ps)
        "${COMPOSE[@]}" "${PROFILES[@]}" ps
        ;;
    logs)
        shift
        "${COMPOSE[@]}" "${PROFILES[@]}" logs -f --tail=100 "$@"
        ;;
    update)
        echo "-> git pull ..."
        git pull
        echo "-> Ziehe ALLE Images (Kern + Backends) ..."
        "${COMPOSE[@]}" "${PROFILES[@]}" pull
        cmd_start
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo "Unbekannter Befehl: $CMD" >&2
        echo
        usage >&2
        exit 1
        ;;
esac
