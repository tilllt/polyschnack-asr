#!/bin/sh
# ==============================================================
# PolySchnack aligner — Entrypoint mit Modell-Selbstheilung (Change 133)
# --------------------------------------------------------------
# Prueft/laedt die 3 Aligner-Modelle (qwen3-forced-aligner,
# TADA-tts-1b + Codec, wav2vec2-xlsr-de) aus den cstr-HF-Repos.
# Fehlt eines, wird es automatisch von HuggingFace geladen; schlaegt
# der Download fehl, gibt der Container eine klare Anleitung aus.
#
# Env (Defaults im Dockerfile):
#   ALIGNER_MODEL_QWEN3      qwen3-FA-GGUF (cstr, mit Mel-Tensoren)
#   ALIGNER_MODEL_TADA       TADA-TTS-Modell
#   ALIGNER_MODEL_TADA_CODEC TADA-Codec-Modell
#   ALIGNER_MODEL_WAV2VEC2   wav2vec2-xlsr-de (CTC-Aligner)
#   HF_TOKEN                 optional, fuer gated Repos
#   ALIGNER_PORT             Server-Port (Default: 5099)
# ==============================================================
set -u

ALIGNER_MODEL_QWEN3="${ALIGNER_MODEL_QWEN3:-/models/qwen3-forced-aligner-0.6b-q8_0.gguf}"
ALIGNER_MODEL_TADA="${ALIGNER_MODEL_TADA:-/models/tada-tts-1b-q4_k.gguf}"
ALIGNER_MODEL_TADA_CODEC="${ALIGNER_MODEL_TADA_CODEC:-/models/tada-codec-f16.gguf}"
ALIGNER_MODEL_WAV2VEC2="${ALIGNER_MODEL_WAV2VEC2:-/models/wav2vec2-large-xlsr-53-german-q4_k.gguf}"
ALIGNER_PORT="${ALIGNER_PORT:-5099}"

is_valid_gguf() {
    # Datei existiert, ist nicht leer und traegt die GGUF-Magic.
    [ -f "$1" ] && [ -s "$1" ] && [ "$(head -c 4 "$1" 2>/dev/null)" = "GGUF" ]
}

# $1 = Pfad, $2 = HF-Repo
ensure_model() {
    _path="$1"
    _repo="$2"
    if is_valid_gguf "$_path"; then
        echo "[aligner] Modell gefunden: $_path"
        return 0
    fi
    if [ -e "$_path" ]; then
        echo "[aligner] WARNUNG: $_path ist keine gueltige GGUF-Datei — lade neu."
        rm -f "$_path" 2>/dev/null || true
    else
        echo "[aligner] Modell fehlt: $_path"
    fi

    _name="$(basename "$_path")"
    _url="https://huggingface.co/${_repo}/resolve/main/${_name}"
    echo "[aligner] Lade Modell herunter: $_url"

    if curl -sSfL --retry 3 --retry-delay 5 \
         ${HF_TOKEN:+-H "Authorization: Bearer ***"} \
         -o "${_path}.tmp" "$_url" \
       && is_valid_gguf "${_path}.tmp"; then
        mv "${_path}.tmp" "$_path"
        echo "[aligner] Download OK: $(du -h "$_path" | cut -f1)"
        return 0
    fi
    rm -f "${_path}.tmp"
    cat <<EOF

======================================================================
[aligner] FEHLER: Modell konnte nicht geladen werden.
  Erwartet: ${_path}
  Quelle:   ${_url}

Moegliche Ursachen:
  - Volume ist read-only gemountet (':ro' in compose.yml) -> ':rw'
  - Kein Internetzugang aus dem Container / HF nicht erreichbar
  - Modellname existiert nicht im Repo ${_repo}

Manueller Download auf dem HOST:
  mkdir -p ./DATA/models
  curl -L -o ./DATA/models/${_name} "${_url}"

Danach Neustart:  docker compose restart crispr-align
======================================================================
EOF
    return 1
}

fail=0
ensure_model "$ALIGNER_MODEL_QWEN3" "cstr/qwen3-forced-aligner-0.6b-GGUF" || fail=1
ensure_model "$ALIGNER_MODEL_TADA" "cstr/tada-tts-1b-GGUF" || fail=1
ensure_model "$ALIGNER_MODEL_TADA_CODEC" "cstr/tada-tts-1b-GGUF" || fail=1
ensure_model "$ALIGNER_MODEL_WAV2VEC2" "cstr/wav2vec2-large-xlsr-53-german-GGUF" || fail=1
[ "$fail" -eq 0 ] || exit 1

echo "[aligner] Starte Forced-Aligner-Service (Port ${ALIGNER_PORT})"
echo "[aligner]   qwen3:     $ALIGNER_MODEL_QWEN3"
echo "[aligner]   tada:      $ALIGNER_MODEL_TADA (+ $ALIGNER_MODEL_TADA_CODEC)"
echo "[aligner]   wav2vec2:  $ALIGNER_MODEL_WAV2VEC2"
exec python3 /aligner_server.py --host 0.0.0.0 --port "$ALIGNER_PORT" "$@"
