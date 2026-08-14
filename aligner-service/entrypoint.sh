#!/bin/sh
# ==============================================================
# PolySchnack aligner — Entrypoint mit Modell-Selbstheilung
# --------------------------------------------------------------
# Wenn das Forced-Aligner-Modell (qwen3-forced-aligner GGUF) fehlt,
# wird es automatisch von HuggingFace geladen. Schlägt der Download
# fehl, gibt der Container eine klare Anleitung aus.
#
# Env:
#   ALIGNER_MODEL   Pfad zum GGUF
#                   (Default: /models/qwen3-forced-aligner-0.6b-f16.gguf)
#   HF_MODEL_REPO   HF-Repo mit dem GGUF
#                   (Default: OpenVoiceOS/qwen3-forced-aligner-0.6b-f16)
#   HF_TOKEN        optional, für gated Repos
#   ALIGNER_PORT    Server-Port (Default: 5099)
# ==============================================================
set -u

ALIGNER_MODEL="${ALIGNER_MODEL:-/models/qwen3-forced-aligner-0.6b-f16.gguf}"
HF_MODEL_REPO="${HF_MODEL_REPO:-OpenVoiceOS/qwen3-forced-aligner-0.6b-f16}"
ALIGNER_PORT="${ALIGNER_PORT:-5099}"

is_valid_gguf() {
    # Datei existiert, ist nicht leer und trägt die GGUF-Magic.
    [ -f "$1" ] && [ -s "$1" ] && [ "$(head -c 4 "$1" 2>/dev/null)" = "GGUF" ]
}

if is_valid_gguf "$ALIGNER_MODEL"; then
    echo "[aligner] Modell gefunden: $ALIGNER_MODEL"
else
    if [ -e "$ALIGNER_MODEL" ]; then
        echo "[aligner] WARNUNG: $ALIGNER_MODEL ist keine gueltige GGUF-Datei — lade neu."
        rm -f "$ALIGNER_MODEL" 2>/dev/null || true
    else
        echo "[aligner] Modell fehlt: $ALIGNER_MODEL"
    fi

    model_name="$(basename "$ALIGNER_MODEL")"
    model_url="https://huggingface.co/${HF_MODEL_REPO}/resolve/main/${model_name}"
    echo "[aligner] Lade Modell herunter (~1,8 GB): $model_url"

    if curl -sSfL --retry 3 --retry-delay 5 \
         ${HF_TOKEN:+-H "Authorization: Bearer ***"} \
         -o "${ALIGNER_MODEL}.tmp" "$model_url" \
       && is_valid_gguf "${ALIGNER_MODEL}.tmp"; then
        mv "${ALIGNER_MODEL}.tmp" "$ALIGNER_MODEL"
        echo "[aligner] Download OK: $(du -h "$ALIGNER_MODEL" | cut -f1)"
    else
        rm -f "${ALIGNER_MODEL}.tmp"
        cat <<EOF

======================================================================
[aligner] FEHLER: Modell konnte nicht geladen werden.
  Erwartet: ${ALIGNER_MODEL}
  Quelle:   ${model_url}

Moegliche Ursachen:
  - Volume ist read-only gemountet (':ro' in compose.yml) -> ':rw'
  - Kein Internetzugang aus dem Container / HF nicht erreichbar
  - Modellname existiert nicht im Repo ${HF_MODEL_REPO}

Manueller Download auf dem HOST:
  mkdir -p ./DATA/models
  curl -L -o ./DATA/models/${model_name} "${model_url}"

Danach Neustart:  docker compose restart crispr-align
(Der Container versucht den Download bei jedem Start automatisch erneut.)
======================================================================
EOF
        exit 1
    fi
fi

echo "[aligner] Starte Forced-Aligner-Service (Port ${ALIGNER_PORT})"
exec python3 /aligner_server.py --model "$ALIGNER_MODEL" --host 0.0.0.0 --port "$ALIGNER_PORT" "$@"
