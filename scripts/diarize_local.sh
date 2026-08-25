#!/usr/bin/env bash
# Manuelle Diarization per CrispASR-CLI (lokal, CPU) — Modell-Vergleichstool.
#
# Nutzt EXAKT die Modelle des Prod-diar-Services (crispr-diar):
#   - ASR:        parakeet-tdt-0.6b-v3-q4_k.gguf  (Prod: ps-pk-onnx)
#   - Diarization: pyannote-seg-3.0.gguf          (Prod: diarize_method=pyannote)
#   - Clustering:  titanet-large.gguf             (stabile Speaker-IDs)
#
# Aufruf:
#   bash diarize_local.sh <audio.mp3|wav> [--method pyannote|foxnose] [--speakers N]
#
# Ausgabe: JSON (voll) + kompakte Speaker-Zeitleiste (stdout).
set -euo pipefail

CLI=/opt/data/crispasr-gpu/build-fix/bin/crispasr
CACHE=/opt/data/home/.cache/crispasr
ASR_MODEL="$CACHE/parakeet-tdt-0.6b-v3-q4_k.gguf"
SEG_MODEL="$CACHE/pyannote-seg-3.0.gguf"
EMB_MODEL="$CACHE/titanet-large.gguf"
WESPEAKER="$CACHE/wespeaker-resnet34-lm.gguf"

AUDIO="${1:?audio fehlt}"
METHOD=pyannote
MAX_SPEAKERS=""
OUT_JSON=""

shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --method) METHOD="$2"; shift 2 ;;
    --speakers) MAX_SPEAKERS="$2"; shift 2 ;;
    --out-json) OUT_JSON="$2"; shift 2 ;;
    *) echo "unbekannt: $1" >&2; exit 2 ;;
  esac
done

[ -f "$AUDIO" ] || { echo "Datei nicht gefunden: $AUDIO" >&2; exit 1; }
[ -f "$CLI" ] || { echo "CLI fehlt: $CLI (erst crispasr bauen)" >&2; exit 1; }

ARGS=(-m "$ASR_MODEL" -f "$AUDIO" -ojf)
case "$METHOD" in
  pyannote)
    ARGS+=(--diarize-speakers) ;;
  foxnose)
    # foxnose BRAUCHT explizit den WeSpeaker-Embedder (nicht TitaNet) —
    # sonst liefert es gar keine Speaker-Labels (CLI-Warnung).
    ARGS+=(--diarize --diarize-method foxnose --diarize-embedder "$WESPEAKER") ;;
  *) echo "methode unbekannt: $METHOD (pyannote|foxnose)" >&2; exit 2 ;;
esac
[ -n "$MAX_SPEAKERS" ] && ARGS+=(--diarize-max-speakers "$MAX_SPEAKERS")

echo "==> Diarization: method=$METHOD audio=$AUDIO" >&2
echo "==> Dauer: $(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$AUDIO" 2>/dev/null)s" >&2
START=$(date +%s)
"$CLI" "${ARGS[@]}" > /tmp/diarize_cli_stdout.txt 2> /tmp/diarize_cli_stderr.txt || {
  echo "FEHLER:" >&2; tail -15 /tmp/diarize_cli_stderr.txt >&2; exit 1; }
END=$(date +%s)
echo "==> fertig in $((END-START))s (CPU)" >&2

JSON=$(ls -t "$(dirname "$AUDIO")"/"$(basename "${AUDIO%.*}")".json "$(dirname "$AUDIO")"/*.json 2>/dev/null | head -1 || true)
[ -n "$OUT_JSON" ] && [ -n "$JSON" ] && cp "$JSON" "$OUT_JSON" 2>/dev/null || true

python3 - "$JSON" <<'PY'
import json, sys, re
p = sys.argv[1] or "/tmp/diarize_cli_stdout.txt"
data = json.load(open(p))
segs = data.get("transcription") or []
if isinstance(segs, dict):
    segs = segs.get("segments", [])
speakers = {}
for s in segs:
    sp = re.sub(r"[()\s]", "", s.get("speaker") or "?") or "?"
    off = s.get("offsets") or {}
    st, en = off.get("from", 0) / 1000.0, off.get("to", 0) / 1000.0
    speakers.setdefault(sp, []).append((st, en))
total = (segs[-1].get("offsets") or {}).get("to", 1) / 1000.0 if segs else 1
print(f"Speaker gesamt: {len(speakers)}")
for sp, spans in sorted(speakers.items()):
    dur = sum(e - st for st, e in spans)
    print(f"  {sp}: {len(spans)} Segmente, {dur:.1f}s ({100*dur/max(total,1):.0f}%)")
print("--- Zeitleiste ---")
for s in segs[:60]:
    off = s.get("offsets") or {}
    sp = re.sub(r"[()\s]", "", s.get("speaker") or "?") or "?"
    print(f"  [{off.get('from',0)/1000:7.2f} -> {off.get('to',0)/1000:7.2f}] {sp}: {(s.get('text') or '')[:80]}")
if len(segs) > 60:
    print(f"  … (+{len(segs)-60} weitere Segmente)")
PY
