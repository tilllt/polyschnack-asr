#!/bin/sh
# Fake CrispASR für Wrapper-Tests: schreibt Standard-JSON aus.
# Versteht die neuen Change-133-Argumente (--align-output statt -o),
# ist aber tolerant: egal welche Argumente reinkommen, das JSON kommt.
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --align-output) out="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cat > "$out" <<'JSON'
{"words": [{"start": 0.0, "end": 0.4, "word": "Hallo"}, {"start": 0.4, "end": 0.9, "word": "Welt"}]}
JSON
echo "aligned ok"
