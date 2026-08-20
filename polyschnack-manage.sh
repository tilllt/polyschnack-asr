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
#               ./DATA/models (idempotent). Modell-Downloads kommen aus
#               backends.yaml (model_files) — nicht hartkodiert. Aktive
#               Backends steuert POLYSCHNACK_BACKENDS in .env (Default:
#               alle; gueltig: Katalog-Namen aus backends.yaml, z. B.
#               crispr-qwen3; alte Kurznamen pk-cpp/qwen3/... funktionieren
#               weiter). Nach dem Aktivieren eines Backends models (oder
#               update) ausfuehren — die Backends mounten ./DATA/models
#               als /models und starten ohne ihre Modelle nicht.
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

# ── Selbst-Update-Metadaten (Change 037) ──────────────────────────────────
# SELFUPDATE_SHA = Commit-SHA des letzten Repo-Commits, der diese Datei
# aenderte (wird beim Committen mitgefuehrt). Basis fuer den Update-Check
# (jeder Lauf) und den selfupdate-Changelog. Deaktivieren des Checks:
# POLYSCHNACK_SELFUPDATE_CHECK=off in der .env.
SELFUPDATE_SHA="6f345df6019542f961d2191ec6b78dd72ccb7666"

# --- Projekt-Basis ----------------------------------------------------------
# compose.backends.yml ist IMMER Teil des Projekts: die Overlays
# (compose.gpu.yml) referenzieren Backend-Services, die sonst ohne
# image/build existieren -> "invalid compose project". Ohne aktivierte
# Profile starten/erstellen die Backends beim up -d trotzdem NICHT.
# Registry-Override: REGISTRY aus .env lesen (z. B. fuer die private
# Dev-Registry) — Env-Variable gewinnt, sonst compose-Default (ghcr.io).
if [ -z "${REGISTRY:-}" ] && [ -f .env ]; then
    REGISTRY="$(grep -E '^REGISTRY=' .env | head -1 | cut -d= -f2- | tr -d '\"' || true)"
    export REGISTRY
fi
COMPOSE=(docker compose -f compose.yml -f compose.backends.yml)

# --- Optionale Backends: welche sind aktiv? ---------------------------------
# Katalog = backends.yaml (webapp/app/backends.yaml, single source of truth):
# dort stehen Name, compose_profile, Modell-Downloads (model_files), Lizenz.
# Auswahl per POLYSCHNACK_BACKENDS in .env (Space-getrennt, Katalog-Namen):
#   POLYSCHNACK_BACKENDS="crispr-qwen3 crispr-ark"
# Alte Kurznamen (pk-cpp qwen3 ark moonshine-de canary) funktionieren weiter
# (werden auf crispr-<name> normalisiert).
# Nur aktive Backends werden provisioniert (Profile) und ihre Modelle gezogen
# (./polyschnack-manage.sh models). Neu aktivierte Backends brauchen danach
# ein `models` (oder `update`) — sonst fehlen die GGUFs beim Start.
BACKENDS_YAML=""
for _cand in webapp/app/backends.yaml; do
    if [ -f "$_cand" ]; then BACKENDS_YAML="$_cand"; break; fi
done

_normalize_backend() {
    case "$1" in
        pk-cpp|qwen3|ark|moonshine-de|canary) echo "crispr-$1" ;;
        *) echo "$1" ;;
    esac
}

_profile_of() {
    # compose_profile aus dem Katalog; ohne Katalog/Eintrag -> Name selbst.
    if [ -n "$BACKENDS_YAML" ]; then
        local p
        p="$(awk -v n="$1" '
            /^  - name:/ { b=$3 }
            /^    compose_profile:/ { if (b==n) { sub(/^    compose_profile: /, ""); print; exit } }
        ' "$BACKENDS_YAML")"
        [ -n "$p" ] && echo "$p" && return
    fi
    echo "$1"
}

BACKENDS_ALL="crispr-pk-cpp crispr-qwen3 crispr-ark crispr-moonshine-de crispr-canary"
if [ -z "${POLYSCHNACK_BACKENDS:-}" ] && [ -f .env ]; then
    # || true: Variable fehlt in .env -> grep exit 1, sonst stiller Abbruch
    # durch set -euo pipefail (Box-Symptom 2026-08-14: alle Befehle still).
    POLYSCHNACK_BACKENDS="$(grep -E '^POLYSCHNACK_BACKENDS=' .env | head -1 | cut -d= -f2- | tr -d '\"' || true)"
fi
# Backend-Auswahl normalisieren (Kurznamen -> Katalog-Namen).
BACKENDS=""
for _b in ${POLYSCHNACK_BACKENDS:-$BACKENDS_ALL}; do
    BACKENDS="$BACKENDS $(_normalize_backend "$_b")"
done
BACKENDS="${BACKENDS# }"

# Profile: Katalog compose_profile (Fallback: Name == Profil). Unbekannte
# Namen im Katalog -> Warnung (Tippfehler / fehlender YAML-Block).
PROFILES=()
for _b in $BACKENDS; do
    _p="$(_profile_of "$_b")"
    if [ "$_p" != "default" ]; then
        PROFILES+=(--profile "$_p")
    fi
    if [ -n "$BACKENDS_YAML" ] && ! awk '/^  - name:/{print $3}' "$BACKENDS_YAML" | grep -qx "$_b"; then
        echo "! Backend '$_b' nicht im Katalog backends.yaml (hinzufuegen oder POLYSCHNACK_BACKENDS pruefen)" >&2
    fi
    if [ -f compose.backends.yml ] && ! grep -qE "^  $_p:" compose.backends.yml; then
        echo "! Backend '$_b': Profil '$_p' nicht in compose.backends.yml (Container-Definition fehlt/auskommentiert)" >&2
    fi
done

# --- Overlays (nur für Start-Kommandos relevant) ---------------------------
# docker info kann HAENGEN (Daemon nicht erreichbar) - mit timeout absichern,
# sonst ist JEDER Befehl (auch help/models) still blockiert.
OVERLAYS=()
echo "-> Pruefe NVIDIA-Container-Runtime ..."
if timeout 5 docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi '"nvidia"'; then
    OVERLAYS+=(-f compose.gpu.yml)
    echo "-> GPU-Overlay aktiv (NVIDIA-Runtime gefunden)"
else
    echo "-> Keine NVIDIA-Runtime (oder Docker nicht erreichbar) - Stack startet CPU-only"
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

_models_from_yaml() {
    # Parser: "backend<TAB>datei<TAB>url" aus den model_files-Maps.
    awk '
        /^  - name:/ { backend=$3; next }
        /model_files:/ { in_models=1; next }
        in_models && /^      [^ :]+: https?:/ {
            line=$0; sub(/^      /, "", line); split(line, kv, ": ");
            print backend "\t" kv[1] "\t" kv[2]
        }
        in_models && /^    [A-Za-z_]+:/ { in_models=0 }
    ' "$1"
}

_licenses_from_yaml() {
    # "backend<TAB>lizenz" aus dem Katalog (z. B. Moonshine CC-BY-NC-SA).
    # Inline-Kommentare (nach #) werden abgeschnitten.
    awk '
        /^  - name:/ { n=$3 }
        /^    license:/ { sub(/^    license: /, ""); sub(/[[:space:]]*#.*$/, ""); print n "\t" $0 }
    ' "$1"
}

cmd_models() {
    mkdir -p DATA/models
    echo "-> Pruefe Backend-Modelle in ./DATA/models (aktive Backends: $BACKENDS)"
    MODELS_SCRIPT=""
    MODEL_FILES=""
    if [ -z "$BACKENDS_YAML" ]; then
        echo "! backends.yaml nicht gefunden (webapp/app/backends.yaml) - bitte selfupdate ausfuehren." >&2
        return 1
    fi
    if [ -z "$BACKENDS" ]; then
        echo "! Keine aktiven Backends (POLYSCHNACK_BACKENDS leer) - nichts zu laden."
        return 0
    fi
    local lb lic
    while IFS=$'\t' read -r lb lic; do
        [ -z "$lb" ] && continue
        case " $BACKENDS " in
            *" $lb "*) ;;
            *) continue ;;
        esac
        echo "  ! Modell-Lizenz beachten: $lb ($lic, ggf. nicht-kommerziell)"
    done < <(_licenses_from_yaml "$BACKENDS_YAML")
    local found=0 b file url
    while IFS=$'\t' read -r b file url; do
        [ -z "$b" ] && continue
        case " $BACKENDS " in
            *" $b "*) ;;
            *) continue ;;
        esac
        found=1
        _model_req "$file" "$url"
    done < <(_models_from_yaml "$BACKENDS_YAML")
    if [ "$found" = 0 ]; then
        echo "-> Keine Backend-Modelle fuer die aktive Auswahl (nichts zu laden)."
    fi
    # Konsistenz: Modellpfade in compose.backends.yml muessen im Katalog stehen.
    if [ -f compose.backends.yml ]; then
        local cm
        while read -r cm; do
            [ -z "$cm" ] && continue
            if ! grep -q "      $cm: https\?" "$BACKENDS_YAML"; then
                echo "  ! WARNUNG: compose.backends.yml nutzt /models/$cm, aber backends.yaml kennt die Datei nicht" >&2
            fi
        done < <(grep -vE '^\s*#' compose.backends.yml | grep -oP '(?<=/models/)[A-Za-z0-9._-]+' | sort -u)
    fi
    if [ -z "$MODELS_SCRIPT" ]; then
        echo "-> Alle Modelle vorhanden - nichts zu laden."
    elif [ -n "$MODELS_SCRIPT" ]; then
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
    if timeout 5 docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi '"nvidia"'; then
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
    if [ -n "$BACKENDS_YAML" ]; then
        echo
        echo "  Katalog (backends.yaml):"
        awk '
            /^  - name:/ { if (n != "") print n "\t" s "\t" l; n=$3; s=""; l="" }
            /^    status:/ { s=$2 }
            /^    license:/ { sub(/^    license: /, "", $0); sub(/[[:space:]]*#.*$/, "", $0); l=$0 }
            END { if (n != "") print n "\t" s "\t" l }
        ' "$BACKENDS_YAML" | awk -F'\t' '{ printf "    %-24s status=%-8s%s\n", $1, $2, ($3 != "" ? "  license=" $3 : "") }'
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

# ── Update-Check (Change 037) ──────────────────────────────────────────────
# Weist auf eine neuere polyschnack-manage.sh hin. Stiller Check (max 5 s),
# Netzwerkfehler werden ignoriert — nie blockieren. Deaktivieren:
# POLYSCHNACK_SELFUPDATE_CHECK=off in der .env.
selfupdate_check() {
    if [ "${POLYSCHNACK_SELFUPDATE_CHECK:-on}" = "off" ]; then
        return 0
    fi
    if [ -z "${SELFUPDATE_SHA:-}" ] || [ "${SELFUPDATE_SHA}" = "PENDING" ]; then
        return 0
    fi
    local url auth=()
    if [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ]; then
        url="${POLYSCHNACK_GITLAB_BASE}/api/v4/projects/tilllt%2Fpolyschnack-asr/repository/files/polyschnack-manage.sh/raw?ref=main"
        auth=(-H "PRIVATE-TOKEN: ${POLYSCHNACK_GITLAB_TOKEN:-}")
    else
        url="https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/polyschnack-manage.sh"
    fi
    local remote
    remote="$(curl -fsSL --max-time 5 "${auth[@]}" "$url" 2>/dev/null | grep -m1 '^SELFUPDATE_SHA=' | cut -d'"' -f2 || true)"
    if [ -z "$remote" ] || [ "$remote" = "$SELFUPDATE_SHA" ]; then
        return 0
    fi
    echo ""
    echo "→ Neuere Version von polyschnack-manage.sh verfügbar (lokal ${SELFUPDATE_SHA:0:7}, remote ${remote:0:7})."
    echo "  Aktualisieren:      ./polyschnack-manage.sh selfupdate"
    echo "  Check deaktivieren: POLYSCHNACK_SELFUPDATE_CHECK=off in .env"
    echo ""
}
if [ "$CMD" != "selfupdate" ] && [ "$CMD" != "help" ] && [ "$CMD" != "-h" ] && [ "$CMD" != "--help" ]; then
    selfupdate_check
fi

case "$CMD" in
    pull)
        echo "-> Ziehe ALLE Images (Kern + Backends) ..."
        "${COMPOSE[@]}" "${PROFILES[@]}" pull
        echo "-> Pull abgeschlossen (Images aktuell oder gezogen)."
        ;;
    start)
        cmd_start
        ;;
    status)
        cmd_status
        ;;
    stop)
        "${COMPOSE[@]}" "${PROFILES[@]}" stop
        echo "-> Alle Container gestoppt."
        ;;
    restart)
        "${COMPOSE[@]}" "${PROFILES[@]}" stop
        echo "-> Alle Container gestoppt."
        cmd_start
        ;;
    down)
        "${COMPOSE[@]}" "${PROFILES[@]}" down
        echo "-> Stack entfernt (Volumes bleiben erhalten)."
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
        # ── Benchmark-Key aus .env nachladen ──────────────────────────────
        # BENCHMARK_API_KEYS/BENCHMARK_API_KEY werden sonst NUR aus der
        # Umgebung gelesen — die .env muss explizit geparst werden (Box-Befund
        # 2026-08-20: Key stand in .env, Skript meldete trotzdem "kein Key").
        if [ -z "${BENCHMARK_API_KEYS:-}" ] && [ -f .env ]; then
            BENCHMARK_API_KEYS="$(grep -E '^BENCHMARK_API_KEYS=' .env | head -1 | cut -d= -f2- | tr -d '\"' || true)"
            export BENCHMARK_API_KEYS
        fi
        if [ -z "${BENCHMARK_API_KEY:-}" ] && [ -f .env ]; then
            BENCHMARK_API_KEY="$(grep -E '^BENCHMARK_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '\"' || true)"
            export BENCHMARK_API_KEY
        fi
        # ── Benchmark-Key (Shared-Key fuer POST /api/benchmark/submit) ─────
        # BENCHMARK_API_KEY = Key fuer den Runner-Container; identischer Wert
        # muss auf Webapp-Seite in BENCHMARK_API_KEYS (Box-.env) stehen,
        # sonst antwortet /submit mit 503/401. Fehlt beides: Key erzeugen,
        # ausgeben und Abbruch — der User traegt ihn in die .env ein.
        if [ -z "${BENCHMARK_API_KEY:-}" ]; then
            if [ -z "${BENCHMARK_API_KEYS:-}" ]; then
                NEW_KEY="$(openssl rand -hex 32 2>/dev/null || true)"
                if [ -z "${NEW_KEY}" ]; then
                    echo "FEHLER: openssl fehlt — Key manuell erzeugen:" >&2
                    echo "  python3 -c 'import secrets; print(secrets.token_hex(32))'" >&2
                    exit 1
                fi
                echo ""
                echo "!! Kein Benchmark-Key konfiguriert (BENCHMARK_API_KEYS fehlt in .env)."
                echo "   Erzeugter Key (einmalig angezeigt):"
                echo ""
                echo "   BENCHMARK_API_KEYS=${NEW_KEY}"
                echo ""
                echo "   So aktivieren (auf der Box):"
                echo "   1. Zeile oben in die .env kopieren"
                echo "   2. ./polyschnack-manage.sh update   (Webapp bekommt die Variable)"
                echo "   3. Diesen Lauf erneut starten."
                echo ""
                echo "   Hinweis: Der Import der vast-Ergebnisse (benchmarks/import/"
                echo "   import_benchmark_suite.sh) nutzt dieselbe Variable."
                echo ""
                exit 1
            fi
            # Erster Key aus der kommaseparierten Liste (Webapp-kompatibel)
            export BENCHMARK_API_KEY="${BENCHMARK_API_KEYS%%,*}"
            echo "-> Benchmark-Key aus BENCHMARK_API_KEYS (.env) uebernommen."
        fi
        # ── Stack-Check: Webapp muss laufen (Benchmark postet an /submit) ──
        # Box-Befund 2026-08-20: benchmark lief, ohne dass der Stack gestartet
        # war — die Ergebnisse wären beim Submit verloren gegangen.
        if ! "${COMPOSE[@]}" ps --status running 2>/dev/null | grep -q 'ps-webapp'; then
            echo ""
            echo "FEHLER: Der PolySchnack-Stack läuft nicht (Container ps-webapp nicht aktiv)." >&2
            echo "  Der Benchmark-Container postet die Ergebnisse an die Webapp" >&2
            echo "  (POST /api/benchmark/submit). Ohne laufende Webapp schlägt der" >&2
            echo "  Submit fehl und die Ergebnisse gehen verloren." >&2
            echo "" >&2
            echo "  Stack starten:  ./polyschnack-manage.sh start" >&2
            echo "  Danach:         ./polyschnack-manage.sh benchmark" >&2
            echo "" >&2
            exit 1
        fi
        # Weicher HTTP-Check: Container läuft, aber antwortet die Webapp?
        # (Nur Warnung — ein vorgeschalteter Reverse-Proxy kann andere Ports nutzen.)
        _webapp_code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "http://localhost:${WEBAPP_PORT:-8088}/" 2>/dev/null || true)"
        if [ -z "$_webapp_code" ] || [ "$_webapp_code" = "000" ]; then
            echo "! Webapp antwortet nicht auf http://localhost:${WEBAPP_PORT:-8088} (HTTP-Check)." >&2
            echo "  Container-Status ok — bitte Port/Erreichbarkeit pruefen." >&2
        fi
        # compose.benchmark.yml fehlt -> Box-Stand veraltet. Klare Meldung
        # statt kryptischem docker-open-Fehler (Box-Befund 2026-08-20).
        if [ ! -f compose.benchmark.yml ]; then
            echo ""
            echo "FEHLER: compose.benchmark.yml fehlt — dieser Stack-Stand ist veraltet." >&2
            echo "  Der Benchmark-Einmal-Container (Change 036) kam mit dieser Compose-Datei." >&2
            echo "" >&2
            echo "  Aktualisieren:  ./polyschnack-manage.sh update" >&2
            echo "  (macht git pull; ohne Git-Repo hier die Datei manuell holen:)" >&2
            echo "  curl -fsSL -o compose.benchmark.yml https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/compose.benchmark.yml" >&2
            echo "" >&2
            exit 1
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
        # Holt neben dem Skript auch backends.yaml (Modell-Katalog) — beide
        # braucht models auf Systemen ohne Git-Checkout (Box).
        _repo_url() {
            if [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ]; then
                echo "${POLYSCHNACK_GITLAB_BASE}/api/v4/projects/tilllt%2Fpolyschnack-asr/repository/files/${1//\//%2F}/raw?ref=main"
            else
                echo "https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/$1"
            fi
        }
        TOKEN="${POLYSCHNACK_GITLAB_TOKEN:-}"
        if [ -z "$TOKEN" ] && [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ] && [ -f .env ]; then
            TOKEN="$(grep -E '^POLYSCHNACK_GITLAB_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '\"' || true)"
        fi
        if [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ] && [ -z "$TOKEN" ]; then
            echo "! POLYSCHNACK_GITLAB_BASE gesetzt - dann braucht selfupdate POLYSCHNACK_GITLAB_TOKEN in .env" >&2
            exit 1
        fi
        CURL_ARGS=(-fsSL --max-time 30)
        if [ -n "$TOKEN" ]; then
            CURL_ARGS+=(-H "PRIVATE-TOKEN: $TOKEN")
        fi
        # 1) backends.yaml (Katalog) — Fehler nur melden, nicht abbrechen.
        BY_TMP="$(mktemp)"
        if curl "${CURL_ARGS[@]}" -o "$BY_TMP" "$(_repo_url webapp/app/backends.yaml)"; then
            if grep -q '^services:' "$BY_TMP" && grep -q 'model_files:' "$BY_TMP"; then
                mkdir -p webapp/app
                mv "$BY_TMP" webapp/app/backends.yaml
                echo "-> backends.yaml aktualisiert."
            else
                rm -f "$BY_TMP"
                echo "! backends.yaml-Download ungueltig - uebersprungen" >&2
            fi
        else
            rm -f "$BY_TMP"
            echo "! backends.yaml konnte nicht geladen werden (models braucht sie)" >&2
        fi
        # 2) manage.sh selbst.
        OLD_SHA="${SELFUPDATE_SHA:-}"
        TMP="$(mktemp)"
        if curl "${CURL_ARGS[@]}" -o "$TMP" "$(_repo_url polyschnack-manage.sh)"; then
            if bash -n "$TMP" && [ "$(wc -c < "$TMP")" -gt 1000 ]; then
                chmod +x "$TMP"
                # Change-History seit der letzten Version (Change 037) —
                # Fehler hier duerfen das Update nie verhindern (|| true).
                if [ -n "$OLD_SHA" ] && [ "$OLD_SHA" != "PENDING" ]; then
                    if [ -n "${POLYSCHNACK_GITLAB_BASE:-}" ]; then
                        COMMITS_URL="${POLYSCHNACK_GITLAB_BASE}/api/v4/projects/tilllt%2Fpolyschnack-asr/repository/commits?path=polyschnack-manage.sh&ref_name=main&per_page=100"
                    else
                        COMMITS_URL="https://api.github.com/repos/tilllt/polyschnack-asr/commits?path=polyschnack-manage.sh&per_page=100"
                    fi
                    echo "→ Änderungen an polyschnack-manage.sh seit ${OLD_SHA:0:7}:"
                    curl "${CURL_ARGS[@]}" "$COMMITS_URL" 2>/dev/null \
                        | sed 's/},{/}\n{/g' \
                        | awk -v old="$OLD_SHA" '
                            # Format-agnostisch: GitLab (id/title/committed_date) und
                            # GitHub (sha/message/commit.author.date). GitHub-JSON
                            # pretty-printet mit Leerzeichen nach ':' -> [ ]*.
                            /"sha":[ ]*"[0-9a-f]{40}"/ { line=$0; sub(/.*"sha":[ ]*"/,"",line); sub(/".*/,"",line); sha=line }
                            /"id":[ ]*"[0-9a-f]{40}"/ { line=$0; sub(/.*"id":[ ]*"/,"",line); sub(/".*/,"",line); sha=line }
                            /"title":[ ]*"/ { line=$0; sub(/.*"title":[ ]*"/,"",line); sub(/".*/,"",line); title=line }
                            /"message":[ ]*"/ { line=$0; sub(/.*"message":[ ]*"/,"",line); sub(/".*/,"",line); title=line }
                            /"committed_date":[ ]*"/ { line=$0; sub(/.*"committed_date":[ ]*"/,"",line); sub(/".*/,"",line); date=line }
                            /"date":[ ]*"[0-9]{4}-[0-9]{2}-[0-9]{2}/ {
                                if (date=="") { line=$0; sub(/.*"date":[ ]*"/,"",line); sub(/".*/,"",line); date=line }
                            }
                            date != "" && title != "" {
                                if (sha==old) exit
                                print "   - " substr(date,1,10) "  " title
                                title=""; date=""
                            }' \
                        | head -30 || true
                fi
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
