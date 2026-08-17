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
#   DIARIZE_METHOD  Diarisierungs-Methode (Default: foxnose)
#                   foxnose = WeSpeaker-Embeddings + Clustering (empfohlen,
#                   mono-tauglich, Auto-Download des 24-MB-Embedder-GGUF)
#                   pyannote = pyannote-seg-3.0-GGUF (Auto-Download)
#                   vad-turns = pausenbasierte Turn-Erkennung (kein Modell)
#                   energy/xcorr = NUR Stereo (auf Mono wirkungslos!)
# ==============================================================
set -u

DIAR_MODEL="${DIAR_MODEL:-/models/parakeet-tdt-0.6b-v3-q8_0.gguf}"
HF_MODEL_REPO="${HF_MODEL_REPO:-cstr/parakeet-tdt-0.6b-v3-GGUF}"
DIAR_PORT="${DIAR_PORT:-5098}"
DIARIZE_METHOD="${DIARIZE_METHOD:-foxnose}"

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
  mkdir -p ./DATA/models
  curl -L -o ./DATA/models/${model_name} "${model_url}"

Danach Neustart:  docker compose restart crispr-diar
(Der Container versucht den Download bei jedem Start automatisch erneut.)
======================================================================
EOF
        exit 1
    fi
fi

echo "[diar] Starte CrispASR-Server (Port ${DIAR_PORT}, Diarize-Methode: ${DIARIZE_METHOD})"

# Diarize-Modell-Downloads (pyannote-seg / WeSpeaker-Embedder) laufen über den
# CrispASR-eigenen Auto-Download (--sherpa-segment-model auto / --diarize-
# embedder auto). CACHE-DIR aufs Modell-Volume legen, damit die Downloads
# Container-Neustarts überleben (Fix 2026-08-15: Diarize lieferte keine
# Speaker, weil der Server ohne --diarize + Segmentierungs-/Embedder-Modell
# gestartet wurde — CrispASR-Doku docs/server.md, docs/cli.md).
export CRISPASR_CACHE_DIR="${CRISPASR_CACHE_DIR:-/models/.crispasr-cache}"

# energy/xcorr brauchen Stereo — unser Client liefert Mono (16 kHz).
# Auf Mono sind sie wirkungslos; deshalb Default auf mono-taugliche Methoden.
case "${DIARIZE_METHOD}" in
  vad-turns)
    DIARIZE_ARGS="--diarize --diarize-method vad-turns"
    ;;
  energy|xcorr)
    echo "[diar] WARNUNG: ${DIARIZE_METHOD} funktioniert nur auf Stereo-Audio — Mono-Aufnahmen erhalten keine Speaker." >&2
    DIARIZE_ARGS="--diarize --diarize-method ${DIARIZE_METHOD}"
    ;;
  *)
    # pyannote (Default) und foxnose. Modell-Strategie: IMMER "auto"
    # (CrispASR-eigener GGUF-Download: pyannote-seg-3.0.gguf ~6 MB +
    # wespeaker-resnet34-lm GGUF ~24 MB, CACHE-DIR aufs Modell-Volume).
    #
    # WARUM NICHT die .onnx-Pfade aus dem Image (DIAR_SEG_MODEL/
    # DIAR_EMBEDDER_MODEL): Der --diarize-embedder-Weg läuft durch
    # wespeaker.cpp, das NUR GGUF lesen kann (gguf_init_from_reader) —
    # eine .onnx-Datei bricht mit "invalid magic characters: '????',
    # expected 'GGUF'" (live auf der Box, 2026-08-17). Der .onnx-Dispatch
    # existiert nur im ORT-POC für pyannote-seg/TitaNet (GPU-Weg), und der
    # ist seit 2026-08-17 widerlegt (6× LANGSAMER als ggml-CPU, s.
    # compose.gpu.yml). Auf CPU/GGUF sind die .onnx-Modelle nutzlos.
    # Fallback auf "auto" war bisher nur aktiv, wenn die ENV fehlt — das
    # Image setzt sie aber immer → Embedder-Fehler. Jetzt: ENVs ignorieren.
    DIARIZE_ARGS="--diarize --diarize-method ${DIARIZE_METHOD} --sherpa-segment-model auto --diarize-embedder auto"
    ;;
esac

exec crispasr --server -m "$DIAR_MODEL" --host 0.0.0.0 --port "$DIAR_PORT" ${DIARIZE_ARGS} "$@"
