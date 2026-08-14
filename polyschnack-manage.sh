#!/usr/bin/env bash
# ==============================================================
# PolySchnack — Stack-Verwaltung (ersetzt start.sh)
# --------------------------------------------------------------
#   ./polyschnack-manage.sh [BEFEHL]   (ohne BEFEHL = Status + Hilfe)
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
#   selfupdate  Aktualisiert DIESES Skript aus dem Repo (GitLab-API, Token
#               aus POLYSCHNACK_GITLAB_TOKEN oder .env daneben).
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
# Registry-Override: REGISTRY aus .env lesen (z. B. fuer die private
# Dev-Registry) — Env-Variable gewinnt, sonst compose-Default (ghcr.io).
if [ -z "${REGISTRY:-}" ] && [ -f .env ]; then
    REGISTRY="$(grep -E '^REGISTRY=' .env | head -1 | cut -d= -f2- | tr -d '"' )"
    export REGISTRY
fi
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
    # WICHTIG: gleiche Overlays wie im Kern-Pass — ohne sie berechnet compose
    # die Kern-Services (ps-webapp/ps-pk-onnx/crispr-diar) OHNE GPU/OIDC-Config
    # neu und recreatet sie (Regression 2026-08-14: OIDC-Login + GPU weg).
    "${COMPOSE[@]}" "${OVERLAYS[@]}" "${PROFILES[@]}" up -d --no-start
    echo
    echo "Fertig. Status:"
    "${COMPOSE[@]}" "${PROFILES[@]}" ps
}

cmd_status() {
    echo "=== GPU ==="
    if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi '"nvidia"'; then
        echo "GPU: JA (NVIDIA-Runtime registriert)"
        if command -v nvidia-smi >/dev/null 2>&1; then
            nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null \
                | sed 's/^/    Gerät: /'
        fi
    else
        echo "GPU: NEIN (keine NVIDIA-Runtime — Stack läuft CPU-only)"
    fi
    echo
    echo "=== Container ==="
    "${COMPOSE[@]}" "${PROFILES[@]}" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null \
        || "${COMPOSE[@]}" "${PROFILES[@]}" ps
    echo
    echo "=== Befehle ==="
    usage
}

usage() {
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

CMD="${1:-status}"
case "$CMD" in
    pull)
        echo "-> Ziehe ALLE Images (Kern + Backends) ..."
        "${COMPOSE[@]}" "${PROFILES[@]}" pull
        ;;
    start)
        cmd_start
        ;;
    status)
        cmd_status
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
        if [ -d .git ]; then
            git pull
        else
            echo "! Kein Git-Repository hier (.git fehlt) — git pull übersprungen."
            echo "  Achtung: compose-Dateien/Skripte manuell aktualisieren,"
            echo "  sonst fehlen neue Services (z.B. crispr-align)."
        fi
        echo "-> Ziehe ALLE Images (Kern + Backends) ..."
        "${COMPOSE[@]}" "${PROFILES[@]}" pull
        cmd_start
        ;;
    selfupdate)
        # Quelle: public GitHub-Mirror (raw.githubusercontent.com, kein Token
        # noetig). In internen Netzen per POLYSCHNACK_GITLAB_BASE auf die
        # GitLab-API umstellen (dann ist POLYSCHNACK_GITLAB_TOKEN noetig).
        if [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ]; then
            URL="${POLYSCHNACK_GITLAB_BASE}/api/v4/projects/tilllt%2Fpolyschnack-asr/repository/files/polyschnack-manage.sh/raw?ref=main"
            TOKEN="${POLYSCHNACK_GITLAB_TOKEN:-}"
            if [ -z "$TOKEN" ] && [ -f .env ]; then
                TOKEN="$(grep -E '^POLYSCHNACK_GITLAB_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '"' )"
            fi
            if [ -z "$TOKEN" ]; then
                echo "! POLYSCHNACK_GITLAB_BASE gesetzt - dann braucht selfupdate POLYSCHNACK_GITLAB_TOKEN in .env" >&2
                exit 1
            fi
        else
            URL="https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/polyschnack-manage.sh"
            TOKEN=""
        fi
        TMP="$(mktemp)"
        CURL_ARGS=(-fsSL --max-time 30)
        if [ -n "$TOKEN" ]; then
            CURL_ARGS+=(-H "PRIVATE-TOKEN: $TOKEN")
        fi
        if curl "${CURL_ARGS[@]}" -o "$TMP" "$URL"; then
            if bash -n "$TMP" && [ "$(wc -c < "$TMP")" -gt 1000 ]; then
                chmod +x "$TMP"
                mv "$TMP" "$0"
                echo "-> Selbst-Update ok. Bitte erneut aufrufen (z.B. ./polyschnack-manage.sh status)."
            else
                rm -f "$TMP"
                echo "! Download ungueltig (Syntax/zu klein) - abgebrochen" >&2
                exit 1
            fi
        else
            rm -f "$TMP"
            echo "! Selbst-Update fehlgeschlagen (Token ungueltig oder Repo nicht erreichbar)" >&2
            exit 1
        fi
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
