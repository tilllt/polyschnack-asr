#!/bin/sh
# Fake qwen3-asr-cli für Wrapper-Tests: schreibt Standard-JSON aus.
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cat > "$out" <<'JSON'
{"words": [{"start": 0.0, "end": 0.4, "word": "Hallo"}, {"start": 0.4, "end": 0.9, "word": "Welt"}]}
JSON
echo "aligned ok"
