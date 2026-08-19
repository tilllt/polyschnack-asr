# Tasks — Change 030

## Phase 1: Webapp-Endpunkte (TDD)

- [ ] T1.1 Tests: `GET /api/benchmark/package` (Determinismus, SHA-Header), `/package/sha256`, `POST /submit` (200/409/422), Re-Pooling nach Submit
- [ ] T1.2 `benchmark_service.py`: `package_sha256(version)`, `build_package_tarball(version)`, `apply_submission(payload)`
- [ ] T1.3 `routers/benchmark.py`: Routen 039/040/041
- [ ] T1.4 CI grün (test-webapp), Commit + Push

## Phase 2: Auto-Run im Benchmark-Container

- [ ] T2.1 `benchmark_selfservice.py` (Paket-Holen, Transkribieren, Submitten)
- [ ] T2.2 `run_container.py`: `BENCH_SUBMIT_URL`/`BENCH_AUTO_SUBMIT` (Post-Submit der `rows` inkl. hyp)
- [ ] T2.3 Dockerfile-Benchmark: Skripte + curl/httpx vorhanden; lokal getestet gegen Dev-Webapp

## Phase 3: Echte CV-Samples

- [ ] T3.1 `prepare.py`-Quellen auf echte `cv/`-Clips umstellen (clean/akzent/kinder + 13 Kanal-Kategorien)
- [ ] T3.2 Neues Manifest bauen (194 Samples), `source`-Feld, Methodik-Text
- [ ] T3.3 Paket bauen (versions/v1 + results), Hash prüfen

## Phase 4: qwen3 + ark (GPU-Debugging)

- [ ] T4.1 vast-Instanz: qwen3-Container-Logs sichern, Start fixen, Suite-Test
- [ ] T4.2 vast-Instanz: ark-UTF-8/leere-Ausgaben fixen, Suite-Test
- [ ] T4.3 Dockerfile/Compose-Fixes committen, CI grün

## Phase 5: Kompletter Neulauf (alle 8 Backends)

- [ ] T5.1 8 Backend-Läufe gegen neues Set (davon neue via selfservice/Submit)
- [ ] T5.2 `latest.json`/`pricing.json` kumulieren, Webapp-Paket bauen
- [ ] T5.3 Zipline-Upload + Hermes-Verzeichnis + Anleitung (wie Change 029-Muster)
- [ ] T5.4 Instanzen destroyen, Kosten-Report
