#!/usr/bin/env bash
# Führt Webapp-Backend-Tests aus (eine Datei oder alle).
set -e
cd /srv/app/pk-asr/webapp
export DATA_DIR=/tmp/ps_debug
if [ -n "$1" ]; then
  .venv/bin/python -m pytest "$1" -q -p no:cacheprovider --tb=short 2>&1 | grep -v "sitecustomize\|importlib.types" | tail -30
else
  for f in tests/test_*.py; do
    echo "--- $f"
    timeout 240 .venv/bin/python -m pytest "$f" -q -p no:cacheprovider --tb=line 2>&1 | grep -v "sitecustomize\|importlib.types" | grep -oE "[0-9]+ (passed|failed)|[0-9]+ passed.*|FAILED.*" | tail -3
  done
fi
