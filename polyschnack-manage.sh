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
#   models      Laedt fehlende GGUF-Modelle der AKTIVEN Backends nach
#               ./DATA/models (idempotent). Aktive Backends steuert
#               POLYSCHNACK_BACKENDS in .env (Default: alle; gueltig:
#               pk-cpp qwen3 ark moonshine-de canary). Nach dem Aktivieren
#               eines Backends models (oder update) ausfuehren — die
#               Backends mounten ./DATA/models als /models und starten
#               ohne ihre Modelle nicht.
#   benchmark   Startet den Benchmark-Einmal-Container (misst die in
#               BENCH_BACKENDS konfigurierten Backends gegen das versionierte
#               Manifest, schreibt results/latest.json + pricing.json ins
#               Volume; die Webapp zeigt sie auf /benchmark). Konfiguration
#               per .env: BENCH_BACKENDS, BENCH_BACKEND_URLS, OPENAI_API_KEY.
#               Container endet nach dem Lauf — ideal fuer Host-Cron.
#   update      git pull + pull + models + start  (kompletter Deploy-Workflow).
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

# --- Optionale Backends: welche sind aktiv? ---------------------------------
# Default: alle. Steuerbar per POLYSCHNACK_BACKENDS in .env (Space-getrennt):
#   POLYSCHNACK_BACKENDS="pk-cpp qwen3"
# Gueltige Namen: pk-cpp qwen3 ark moonshine-de canary.
# Nur aktive Backends werden provisioniert (Profile) und ihre Modelle gezogen
# (./polyschnack-manage.sh models). Neu aktivierte Backends brauchen danach
# ein `models` (oder `update`) — sonst fehlen die GGUFs beim Start.
BACKENDS_ALL="pk-cpp qwen3 ark moonshine-de canary"
if [ -z "${POLYSCHNACK_BACKENDS:-}" ] && [ -f .env ]; then
    POLYSCHNACK_BACKENDS="$(grep -E '^POLYSCHNACK_BACKENDS=' .env | head -1 | cut -d= -f2- | tr -d '\"' )"
fi
BACKENDS="${POLYSCHNACK_BACKENDS:-$BACKENDS_ALL}"
PROFILES=()
for _b in $BACKENDS; do
    case "$_b" in
        pk-cpp)       PROFILES+=(--profile crispr-pk-cpp) ;;
        qwen3)        PROFILES+=(--profile crispr-qwen3) ;;
        ark)          PROFILES+=(--profile crispr-ark) ;;
        moonshine-de) PROFILES+=(--profile crispr-moonshine-de) ;;
        canary)       PROFILES+=(--profile crispr-canary) ;;
        *)            echo "! Unbekanntes Backend in POLYSCHNACK_BACKENDS: $_b (gueltig: $BACKENDS_ALL)" >&2 ;;
    esac
done

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

# --- Modelle: nur fuer konfigurierte Backends -------------------------------
# Helper: traegt fehlende Modelle in die Download-Liste ein (idempotent).
MODELS_SCRIPT=""
MODEL_FILES=""
_model_req() {
    local file="$1" url="$2"
    if [ -s "DATA/models/$file" ]; then
        echo "  ok   $file"
    else
        echo "  fehlt $file -> lade ..."
        MODELS_SCRIPT="$MODELS_SCRIPT [ -s /models/$file ] || wget -qO /models/$file '$url' || true;"
        MODEL_FILES="$MODEL_FILES $file"
    fi
}

cmd_models() {
    mkdir -p DATA/models
    echo "-> Pruefe Backend-Modelle in ./DATA/models (aktive Backends: $BACKENDS)"
    MODELS_SCRIPT=""
    MODEL_FILES=""
    for _b in $BACKENDS; do
        case "$_b" in
            pk-cpp)
                _model_req parakeet-tdt-0.6b-v3-q8_0.gguf "https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf" ;;
            qwen3)
                _model_req qwen3-asr-0.6b-q8_0.gguf "https://huggingface.co/OpenVoiceOS/qwen3-asr-0.6b-q8-0/resolve/main/qwen3-asr-0.6b-q8_0.gguf"
                _model_req qwen3-forced-aligner-0.6b-f16.gguf "https://huggingface.co/OpenVoiceOS/qwen3-forced-aligner-0.6b-f16/resolve/main/qwen3-forced-aligner-0.6b-f16.gguf" ;;
            ark)
                _model_req ark-asr-3b-q8_0.gguf "https://huggingface.co/cstr/ark-asr-3b-GGUF/resolve/main/ark-asr-3b-q8_0.gguf" ;;
            moonshine-de)
                echo "  ! moonshine-de: Modell ist CC-BY-NC-SA-4.0 (nicht-kommerziell)"
                _model_req moonshine-base-de-fidoriel-q4_k.gguf "https://huggingface.co/cstr/moonshine-base-de-fidoriel-GGUF/resolve/main/moonshine-base-de-fidoriel-q4_k.gguf"
                _model_req tokenizer.bin "https://huggingface.co/cstr/moonshine-base-de-fidoriel-GGUF/resolve/main/tokenizer.bin" ;;
            canary)
                _model_req canary-1b-v2-q4_k.gguf "https://huggingface.co/cstr/canary-1b-v2-GGUF/resolve/main/canary-1b-v2-q4_k.gguf" ;;
        esac
    done
    if [ -n "$MODELS_SCRIPT" ]; then
        echo "-> Lade fehlende Modelle (einmalig docker run alpine) ..."
        docker run --rm -v "$PWD/DATA/models:/models" alpine sh -c "$MODELS_SCRIPT ls -lh /models" || true
    fi
    local missing=0
    for f in $MODEL_FILES; do
        if [ ! -s "DATA/models/$f" ]; then
            echo "  FEHLER: $f konnte nicht geladen werden (Netz/HuggingFace?)" >&2
            missing=1
        fi
    done
    if [ "$missing" != 0 ]; then
        echo "! Modelle unvollstaendig - Start der betroffenen Backends wird fehlschlagen" >&2
        return 1
    fi
    echo "-> Modelle fertig."
}

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
    echo "=== Backends (POLYSCHNACK_BACKENDS) ==="
    echo "  Aktiv: $BACKENDS"
    echo "  (Modelle: ./polyschnack-manage.sh models)"
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
    models)
        cmd_models
        ;;
    benchmark)
        echo "-> Benchmark-Einmal-Lauf (Container endet nach dem Lauf) ..."
        # REGISTRY kommt aus .env (oben exportiert) — das Benchmark-Image
        # liegt nur in der Dev-Registry, nicht auf GHCR.
        # BENCH_BACKEND_URLS-Default: JSON darf kein '}' in Compose-Defaults
        # enthalten — der Default lebt deshalb hier (in .env ueberschreibbar,
        # z. B. fuer externe OpenAI-Endpunkte).
        if [ -z "${BENCH_BACKEND_URLS:-}" ]; then
            BENCH_BACKEND_URLS='{"ps-pk-onnx":"http://ps-pk-onnx:5092/v1","crispr-pk-cpp":"http://crispr-pk-cpp:5093/v1","crispr-qwen3":"http://crispr-qwen3:5094/v1","crispr-ark":"http://crispr-ark:5095/v1","crispr-moonshine-de":"http://crispr-moonshine-de:5096/v1","crispr-canary":"http://crispr-canary:5097/v1"}'
            export BENCH_BACKEND_URLS
        fi
        docker compose -f compose.yml -f compose.benchmark.yml run --rm benchmark
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
        cmd_models
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
