#!/usr/bin/env bash
# ============================================================================
# import_benchmark_suite.sh — hash-gesicherter Benchmark-Suite-Import (Change 036)
#
# Zweck: Die aktuelle 207er-Suite + die vast-Benchmark-Ergebnisse auf die
# deployte PolySchnack-Instanz bringen — IMMER mit package_sha256-Verifikation:
#   * Paket-Hash wird beim Entpacken geprüft (sha256.txt vs. Neuberechnung)
#   * IST-Grundlage (Box-Volume) wird gehasht und mit dem Paket verglichen
#   * Neue Suite wird als NEUE Version vN+1 eingespielt (nie überschreiben),
#     Manifest wird finalisiert (version/supersedes) und der FINALE Hash
#     danach berechnet — mit genau dieser SHA laufen die Submits.
#   * Ergebnisse laufen über den offiziellen POST /api/benchmark/submit
#     (HMAC-SHA256 + Shared-Key); idempotent (Run-IDs).
#
# Aufruf (auf der Box, im polyschnack-Checkout):
#   ./import_benchmark_suite.sh <PAKET> [Optionen]
#     PAKET: Zipline-URL (https://drop.n0ne.de/u/xxx.tar.gz) oder lokale Datei
#     --benchmark-dir DIR  Default: ./DATA/poc-data/benchmark
#     --api URL            Default: https://whisper.cia-spandau.de
#     --key KEY            Default: 1. Key aus BENCHMARK_API_KEYS der .env
#     --results DIR        Default: ./results  (result_benchmark_*.json)
#     --yes                Rückfragen überspringen
#
# Voraussetzung: Webapp-Image mit Change 036 (backends.yaml enthält
# whisper-large-v3 + voxtral-mini-realtime) — sonst bricht der Submit mit
# "unknown backend" ab. python3 (stdlib) muss vorhanden sein.
# ============================================================================
set -euo pipefail

PAKET="${1:?Aufruf: ./import_benchmark_suite.sh <paket.tar.gz|URL> [Optionen]}"
BENCH_DIR="${BENCH_DIR:-./DATA/poc-data/benchmark}"
API_URL="${API_URL:-https://whisper.cia-spandau.de}"
RESULT_DIR="${RESULT_DIR:-./results}"
YES=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/suite_import.py"

while [ $# -gt 1 ]; do
  case "$2" in
    --benchmark-dir) BENCH_DIR="$3"; shift 2 ;;
    --api)           API_URL="$3";  shift 2 ;;
    --key)           KEY="$3";      shift 2 ;;
    --results)       RESULT_DIR="$3"; shift 2 ;;
    --yes)           YES=1;         shift ;;
    *) shift ;;
  esac
done

if [ -z "${KEY:-}" ]; then
  KEY="$(grep -m1 '^BENCHMARK_API_KEYS=' .env 2>/dev/null | cut -d= -f2- | cut -d, -f1 | tr -d ' \r\n' || true)"
fi
if [ -z "${KEY:-}" ]; then
  echo "FEHLER: Kein Benchmark-Key gefunden (--key oder BENCHMARK_API_KEYS in .env)."
  echo ""
  echo "  Key erzeugen:       openssl rand -hex 32"
  echo "  In die Box-.env:    BENCHMARK_API_KEYS=<key>"
  echo "  Webapp neu starten: ./polyschnack-manage.sh deploy   (bzw. docker compose up -d ps-webapp)"
  echo "  Alternativ direkt:  ./import_benchmark_suite.sh <PAKET> --key <key>"
  exit 1
fi

TMP="$(mktemp -d /tmp/benchmark_suite.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
echo "== 1/7 Paket holen"
if [[ "$PAKET" == http* ]]; then
  curl -sL --fail -o "$TMP/paket.tar.gz" "$PAKET"
else
  cp "$PAKET" "$TMP/paket.tar.gz"
fi
tar -xzf "$TMP/paket.tar.gz" -C "$TMP"
[ -f "$TMP/sha256.txt" ] || { echo "FEHLER: sha256.txt fehlt im Paket"; exit 1; }
PAK_SHA=$(cat "$TMP/sha256.txt" | tr -d ' \r\n')
[ -n "$PAK_SHA" ] || { echo "FEHLER: leere SHA im Paket"; exit 1; }

echo "== 2/7 Paket-Hash verifizieren (sha256.txt vs. Neuberechnung)"
CALC_SHA=$(python3 "$PY" compute-sha "$TMP"/versions/v[0-9]*)
if [ "$PAK_SHA" != "$CALC_SHA" ]; then
  echo "FEHLER: Paket-Hash mismatch: sha256.txt=$PAK_SHA berechnet=$CALC_SHA"; exit 1
fi
echo "  Paket-Hash OK: $PAK_SHA"

echo "== 3/7 IST-Grundlage der Box hashen"
IST_VER=$(python3 "$PY" latest-version "$BENCH_DIR")
if [ "$IST_VER" -gt 0 ]; then
  IST_SHA=$(python3 "$PY" compute-sha "$BENCH_DIR/versions/v$IST_VER")
else
  IST_SHA="(keine Version)"
fi
echo "  IST: v$IST_VER  sha=$IST_SHA"
echo "  NEU: Paket sha=$PAK_SHA"

if [ "$IST_SHA" = "$PAK_SHA" ]; then
  echo "== 4/7 Grundlage identisch — keine neue Version nötig (nur Results)"
  NEW_VER=$IST_VER; NEW_SHA=$PAK_SHA
else
  echo "== 4/7 Neue Suite wird als Version v$((IST_VER+1)) eingespielt (supersedes=v$IST_VER)"
  if [ "$YES" -eq 0 ]; then
    read -r -p "  Einspielen? [j/N] " a
    [[ "$a" =~ ^[jJyY] ]] || { echo "Abbruch."; exit 0; }
  fi
  OUT=$(python3 "$PY" prepare "$TMP" "$BENCH_DIR")
  echo "$OUT"
  NEW_VER=$(echo "$OUT" | sed -n 's/^VERSION=//p')
  NEW_SHA=$(echo "$OUT" | sed -n 's/^SHA=//p')
  [ -n "$NEW_SHA" ] || { echo "FEHLER: prepare lieferte keine SHA"; exit 1; }
fi
echo "  Aktiv: v$NEW_VER sha=$NEW_SHA"

echo "== 5/7 Results submitten (POST /api/benchmark/submit, HMAC-SHA256)"
RUNS_DIR="$BENCH_DIR/results/runs"
mkdir -p "$RUNS_DIR"
FOUND=0; OK=0; SKIP=0; FAIL=0
for rf in "$RESULT_DIR"/result_benchmark_*.json; do
  [ -f "$rf" ] || continue
  FOUND=$((FOUND+1))
  B=$(basename "$rf")
  echo "  -- $B"
  if [ "$YES" -eq 0 ]; then
    read -r -p "     submiten? [j/N] " a
    [[ "$a" =~ ^[jJyY] ]] || { echo "     übersprungen."; continue; }
  fi
  OUT=$(PYTHONPATH="$HERE" python3 - "$rf" "$NEW_VER" "$NEW_SHA" "$API_URL" "$KEY" "$RUNS_DIR" <<'PYEOF'
import json, sys
from suite_import import build_payload, submit
from pathlib import Path
rf, ver, sha, api, key, runs = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5], Path(sys.argv[6])
res = json.load(open(rf, encoding='utf-8'))
payload = build_payload(res, ver, sha)
try:
    r = submit(payload, api, key, runs_dir=runs)
    if r.get('skipped'):
        print('SKIPPED (bereits eingespielt)')
    elif r.get('ok'):
        print(f"OK backend={payload['backend']} rows={len(payload['rows'])} runs_file={r.get('runs_file')}")
    else:
        print(f"ABGELEHNT: {json.dumps(r, ensure_ascii=False)[:300]}")
        sys.exit(3)
except Exception as e:
    print(f"FEHLER: {e}")
    sys.exit(3)
PYEOF
)
  RC=$?
  echo "$OUT"
  if [ "$RC" -eq 0 ]; then
    if [[ "$OUT" == SKIPPED* ]]; then SKIP=$((SKIP+1)); else OK=$((OK+1)); fi
  else
    FAIL=$((FAIL+1))
    if [[ "$OUT" == *unknown\ backend* ]]; then
      echo "!! Backend nicht registriert — Webapp-Image mit Change 036 deployen (docker compose pull/up -d), dann erneut ausführen."
    fi
  fi
done
echo "  Gefunden=$FOUND OK=$OK übersprungen=$SKIP fehlgeschlagen=$FAIL"

echo "== 6/7 Ergebnis prüfen (GET /api/benchmark/results)"
curl -s --fail "$API_URL/api/benchmark/results" | python3 -c "
import json, sys
d = json.load(sys.stdin)
rows = sorted(d.get('rows', []), key=lambda r: r.get('wer', 1))
print(f\"  Version {d.get('version')} · {d.get('run_id')}\")
for r in rows:
    print(f\"  {r['backend']:<22} WER {r['wer']:.4f}  RTF {r.get('rtf', 0):.4f}  n={r.get('n_samples')}\")
"

echo "== 7/7 Fertig. GUI: https://$API_URL/benchmark"
