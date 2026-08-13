#!/bin/sh
# ==============================================================
# PolySchnack diar — Entrypoint mit Modell-Selbstheilung
# --------------------------------------------------------------
# Wenn das ASR-Modell (parakeet-GGUF) fehlt, wird es automatisch
# von HuggingFace geladen. Schlägt der Download fehl, gibt der
# Container eine klare Anleitung aus, statt kryptisch zu crashen.
#
# Env:
#   DIAR_MODEL      Pfad zum GGUF
#                   (Default: /models/parakeet-tdt-0.6b-v3-q8_0.gguf)
#   HF_MODEL_REPO   HF-Repo mit den GGUFs
#                   (Default: cstr/parakeet-tdt-0.6b-v3-GGUF)
#   HF_TOKEN        optional, für gated Repos
#   DIAR_PORT       Server-Port (Default: 5098)
# ==============================================================
set -u

DIAR_MODEL="${DIAR_MODEL:-/models/parakeet-tdt-0.6b-v3-q8_0.gguf}"
HF_MODEL_REPO="${HF_MODEL_REPO:-cstr/parakeet-tdt-0.6b-v3-GGUF}"
DIAR_PORT="${DIAR_PORT:-5098}"

is_valid_gguf() {
    # Datei existiert, ist nicht leer und trägt die GGUF-Magic.
    [ -f "$1" ] && [ -s "$1" ] && [ "$(head -c 4 "$1" 2>/dev/null)" = "GGUF" ]
}

if is_valid_gguf "$DIAR_MODEL"; then
    echo "[diar] Modell gefunden: $DIAR_MODEL"
else
    if [ -e "$DIAR_MODEL" ]; then
        echo "[diar] WARNUNG: $DIAR_MODEL ist keine gueltige GGUF-Datei — lade neu."
        rm -f "$DIAR_MODEL" 2>/dev/null || true
    else
        echo "[diar] Modell fehlt: $DIAR_MODEL"
    fi

    model_name="$(basename "$DIAR_MODEL")"
    model_url="https://huggingface.co/${HF_MODEL_REPO}/resolve/main/${model_name}"
    echo "[diar] Lade Modell herunter: $model_url"

    if curl -sSfL --retry 3 --retry-delay 5 \
         ${HF_TOKEN:+-H "Authorization: Bearer ${HF_TOKEN}"} \
         -o "${DIAR_MODEL}.tmp" "$model_url" \
       && is_valid_gguf "${DIAR_MODEL}.tmp"; then
        mv "${DIAR_MODEL}.tmp" "$DIAR_MODEL"
        echo "[diar] Download OK: $(du -h "$DIAR_MODEL" | cut -f1)"
    else
        rm -f "${DIAR_MODEL}.tmp"
        cat <<EOF

======================================================================
[diar] FEHLER: Modell konnte nicht geladen werden.
  Erwartet: ${DIAR_MODEL}
  Quelle:   ${model_url}

Moegliche Ursachen:
  - Volume ist read-only gemountet (':ro' in compose.yml) -> ':rw'
  - Kein Internetzugang aus dem Container / HF nicht erreichbar
  - Modellname existiert nicht im Repo ${HF_MODEL_REPO}

Manueller Download auf dem HOST:
  mkdir -p ./DATA/diar-models
  curl -L -o ./DATA/diar-models/${model_name} "${model_url}"

Danach Neustart:  docker compose restart crispr-diar
(Der Container versucht den Download bei jedem Start automatisch erneut.)
======================================================================
EOF
        exit 1
    fi
fi

echo "[diar] Starte CrispASR-Server (Port ${DIAR_PORT})"
exec crispasr --server -m "$DIAR_MODEL" --host 0.0.0.0 --port "$DIAR_PORT" "$@"
