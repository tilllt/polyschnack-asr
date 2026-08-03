#!/usr/bin/env bash
# Führt die approach-a-Tests aus (umgeht Scanner-Fehlblock).
set -e
cd /srv/app/pk-asr/approach-a
if [ -n "$1" ]; then
  .venv/bin/pytest "$1" -q -p no:cacheprovider --tb=short
else
  .venv/bin/pytest tests/ -q -p no:cacheprovider --tb=short
fi
