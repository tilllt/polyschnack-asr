#!/usr/bin/env bash
# ============================================================
# Aligner-Benchmark: qwen3-forced-aligner vs TADA vs wav2vec2
# (alle lokal, CPU) — PolySchnack Change 130 + Suite-Erweiterung
#
# Metriken pro Aligner auf derselben Datei + Referenztext:
#   - alignierte Wörter / Referenzwörter (Abdeckung)
#   - 0-Dauer-Wörter (Fehler)
#   - Zeitspanne (letztes end), Laufzeit, Modellgröße
#   - paarweise Δ der Wort-Timestamps (Kreuzvergleich)
#
# Aufruf: bash aligner_bench.sh <audio.wav|mp3> <ref-text.txt>
# Audio muss 16k mono sein (werden wir selbst konvertieren).
# ============================================================
set -euo pipefail

AUDIO="${1:?audio fehlt}"
REFTEXT="${2:?referenztext-datei fehlt}"
OUTDIR="${3:-/opt/data/pk-asr/benchmark/aligner}"
mkdir -p "$OUTDIR"

WAV16="$OUTDIR/audio_16k.wav"
ffmpeg -v error -y -i "$AUDIO" -ac 1 -ar 16000 "$WAV16"
TEXT=$(cat "$REFTEXT")
DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$WAV16")

QWEN=/opt/data/sep-test/qwen3-asr/build/qwen3-asr-cli
QWEN_MODEL=/opt/data/sep-test/models/qwen3-forced-aligner-0.6b-f16.gguf
CRISP=/opt/data/crispasr-gpu/build-fix/bin/crispasr
TADA_MODEL=/tmp/tada-tts-1b-q4_k.gguf
TADA_CODEC=/tmp/tada-codec-f16.gguf
W2V=/tmp/wav2vec2-xlsr-de-q4_k.gguf

echo "==> Audio: $AUDIO (${DUR}s) | Referenz: $(echo "$TEXT" | wc -w) Wörter"

# --- qwen3-forced-aligner (aktueller PolySchnack-Aligner) ---
echo "--- qwen3 ---"
S=$(date +%s%N)
"$QWEN" -m "$QWEN_MODEL" -f "$WAV16" --align --text "$TEXT" --lang de \
  -o "$OUTDIR/qwen.json" > "$OUTDIR/qwen.log" 2>&1 || true
E=$(date +%s%N)
echo "$(( (E-S)/1000000 )) ms" > "$OUTDIR/qwen.time"
tail -2 "$OUTDIR/qwen.log" | head -1

# --- TADA (CrispASR --align, de-Aligner) ---
echo "--- tada ---"
[ -f /tmp/tada-aligner-en.gguf ] || cp /opt/data/home/.cache/crispasr/tada-aligner-de.gguf /tmp/tada-aligner-en.gguf
[ -f /tmp/tada-encoder-f16.gguf ] || cp /opt/data/home/.cache/crispasr/tada-encoder-f16.gguf /tmp/tada-encoder-f16.gguf
S=$(date +%s%N)
"$CRISP" -m "$TADA_MODEL" --codec-model "$TADA_CODEC" --align \
  --voice "$WAV16" --ref-text "$TEXT" --align-format json \
  --align-output "$OUTDIR/tada.json" > "$OUTDIR/tada.log" 2>&1 || true
E=$(date +%s%N)
echo "$(( (E-S)/1000000 )) ms" > "$OUTDIR/tada.time"
grep -E "words" "$OUTDIR/tada.log" | tail -1 || true

# --- wav2vec2-xlsr-de (CTC forced alignment) ---
echo "--- wav2vec2 ---"
S=$(date +%s%N)
"$CRISP" --align-only -am "$W2V" -f "$WAV16" --ref-text "$TEXT" \
  --align-format json --align-output "$OUTDIR/wav2vec.json" \
  > "$OUTDIR/wav2vec.log" 2>&1 || true
E=$(date +%s%N)
echo "$(( (E-S)/1000000 )) ms" > "$OUTDIR/wav2vec.time"
grep -E "words" "$OUTDIR/wav2vec.log" | tail -1 || true

echo "==> fertig. JSONs in $OUTDIR"
