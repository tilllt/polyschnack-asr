# Change 148 — Tasks (deterministische Pakete)

## 1. Root Cause

- [x] `tarfile.open(mode="w:gz")` schreibt die AKTUELLE ZEIT in den
      gzip-Header → Byte-Drift, wenn zwei Aufrufe in verschiedenen
      Sekunden erfolgen (Timing-Flake)

## 2. Fix

- [x] `benchmark_service.build_package_tarball`: tar im GNU-Format +
      separater gzip-Schritt mit `mtime=0`
- [x] `routers/benchmark.py` `vad_package` + `diar_package`: gleiches Muster
- [x] Verifikation: Determinismus-Test 10× grün (vorher 1× failed von 3);
      Benchmark-Suite 61 Tests grün