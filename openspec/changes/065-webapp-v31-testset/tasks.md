# Change 065 — Tasks

## 1. Paket-Import (`webapp/app/benchmark_service.py`)

- [x] `build_vad_package`: V3.1-public aus GitHub-Release v4 importieren
      (URL `…/download/v4/vad-benchmark-v3.1-public.zip`), SHA256-Check
      gegen `b48bb9e9abd5a4a69c6a8fc9848a563daea0056813d3d6716e5aa5abee9b9788`
      (Config: VAD_PACKAGE_URL/VAD_PACKAGE_SHA256, Tests via file://-Fixture)
- [x] Cache unter `versions/v{N}/vad/` (ZIP + import/; erneuter Import bei
      fehlendem vad-manifest.json)
- [x] `testset.json`-Samples auf vad-manifest-Schema mappen (id, source,
      variant, split, gt); WAVs kopieren; `testset_version` (z. B. "v4-public")
      + `testset_release_url` ins Manifest
- [x] Offline-Verhalten: SHA256-Mismatch → RuntimeError (kein stiller
      Fallback auf das alte Set)
- [x] `vad_package_sha256` bleibt (Hash über Manifest + WAVs, sortiert)

## 2. Endpoints (`webapp/app/routers/benchmark.py`)

- [x] `GET /vadpackage/sha256` → `{version, sha256, testset_version,
      release_url}`
- [x] `GET /vadpackage` → X-Benchmark-SHA256 wie gehabt; body unverändert
      (Submitter liest vad-manifest.json → automatisch V3.1)
- [x] Bugfix (aus Change 062): `_vad_summary` bekam den ASR-Paket-Hash
      statt des VAD-Hash → VAD-Sektion blieb immer leer. Jetzt berechnet
      `_vad_summary` den VAD-Hash selbst + testset_version aus dem Manifest.

## 3. Frontend

- [x] `benchmark.ts`: `VadResultRow` + `testset_version?`, `testset_release_url?`
- [x] `BenchmarkPage.tsx`: VAD-Sektion zeigt Testset-Version + Release-Link
      (über der Tabelle); Leer-Hinweis unverändert
- [x] Tests: 1 neuer Frontend-Test (Versions-Anzeige + Link)

## 4. Backend-Tests

- [x] Paket-Import-Test (file://-ZIP-Fixture, kein Netz): Samples = 3,
      testset_version "v4-public", SHA stabil
- [x] `_vad_summary` enthält testset_version + release_url
      (test_vad_submit_ok_pools_separately erweitert)
- [x] Neu: `test_vadpackage_sha256_reports_testset_version`
- [x] Backend-Submit-Tests: 21/21 grün; Frontend 236/236 + tsc + build ok
- [ ] Vollsuite `run_full_suite.sh` fail=0 (läuft)

## 5. Abschluss

- [ ] Commit + Push + CI prüfen
- [ ] VAD-Submits gegen V3.1-Paket (BENCHMARK_API_KEYS lokal vorhanden):
      lokale Läufe mit `vad_selfservice.py` (public nur; heldout bleibt lokal)
- [ ] component-decisions.md: Hinweis, dass Webapp-Benchmark jetzt auf
      V3.1-public läuft
