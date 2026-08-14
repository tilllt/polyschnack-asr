#!/usr/bin/env bash
# Kompletter Backend-Testlauf der Webapp — Ergebnisse nach Datei in /tmp.
set -u
cd "$(dirname "$0")"
export DATA_DIR=/tmp/ps_debug
OUT=/tmp/ps_full_suite.log
: > "$OUT"
fail=0
for f in tests/test_*.py; do
  name=$(basename "$f")
  echo "=== $name" >> "$OUT"
  timeout 600 .venv/bin/python -m pytest "$f" -q --tb=line -p no:cacheprovider \
    2>&1 | grep -vE "sitecustomize|importlib.types" | grep -E "passed|failed|error" | tail -2 >> "$OUT"
  rc=${PIPESTATUS[0]}
  if [ $rc -ne 0 ]; then fail=1; fi
done
echo "=== GESAMT fail=$fail" >> "$OUT"
exit $fail
