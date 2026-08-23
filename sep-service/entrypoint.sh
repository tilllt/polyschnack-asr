#!/bin/sh
# ==============================================================
# PolySchnack crispr-sep — Entrypoint mit Modell-Selbstheilung
# --------------------------------------------------------------
# Wenn eines der Source-Separation-Modelle (htdemucs / mel-band-
# roformer, GGUF von cstr) fehlt, wird es automatisch von
# HuggingFace geladen. Schlägt ein Download fehl, startet der
# Server trotzdem — /health zeigt dann, welches Backend fehlt,
# und /v1/audio/separate antwortet für dieses Backend mit 422.
#
# Env:
#   SEP_HTDEMUCS_MODEL   Pfad zum htdemucs-GGUF
#                        (Default: /models/htdemucs-f16.gguf)
#   SEP_MELBAND_MODEL    Pfad zum mel-band-roformer-GGUF
#                        (Default: /models/mel-band-roformer-vocals-f16.gguf)
#   SEP_PORT             Server-Port (Default: 5100)
# ==============================================================
set -u

SEP_HTDEMUCS_MODEL="${SEP_HTDEMUCS_MODEL:-/models/htdemucs-f16.gguf}"
SEP_MELBAND_MODEL="${SEP_MELBAND_MODEL:-/models/mel-band-roformer-vocals-f16.gguf}"
SEP_PORT="${SEP_PORT:-5100}"

is_valid_gguf() {
    # Datei existiert, ist nicht leer und trägt die GGUF-Magic.
    [ -f "$1" ] && [ -s "$1" ] && [ "$(head -c 4 "$1" 2>/dev/null)" = "GGUF" ]
}

fetch_if_missing() {
    # $1 = Modellpfad, $2 = HF-Repo, $3 = Anzeigename
    if is_valid_gguf "$1"; then
        echo "[sep] $3 gefunden: $1"
    else
        if [ -e "$1" ]; then
            echo "[sep] WARNUNG: $1 ist keine gueltige GGUF-Datei — lade neu."
            rm -f "$1" 2>/dev/null || true
        else
            echo "[sep] $3 fehlt: $1"
        fi
        model_name="$(basename "$1")"
        model_url="https://huggingface.co/${2}/resolve/main/${model_name}"
        echo "[sep] Lade $3 herunter: $model_url"
        wget -q --show-progress -O "$1" "$model_url" \
            && echo "[sep] $3 geladen ($(du -h "$1" | cut -f1))" \
            || echo "[sep] FEHLER: Download von $3 fehlgeschlagen — Backend bleibt deaktiviert."
    fi
}

fetch_if_missing "$SEP_HTDEMUCS_MODEL" "cstr/htdemucs-GGUF" "htdemucs"
fetch_if_missing "$SEP_MELBAND_MODEL" "cstr/mel-band-roformer-vocals-GGUF" "mel-band-roformer"

echo "[sep] Starte Source-Separation-Service (Port $SEP_PORT)"
exec python3 /sep_server.py --port "$SEP_PORT"
