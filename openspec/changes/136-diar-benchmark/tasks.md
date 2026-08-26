# Change 136 — Tasks

## 0. Lizenz-Klärung (vor Package-Bau) — ERLEDIGT 26.08.

- [x] CC-BY-NC-SA (TalkBank/HF) vs. LDC97S43 (kommerziell): geprüft —
      **CALLHOME German verworfen** (HF gated: 401 ohne Token / 403 mit
      Token; CC-BY-NC-SA ungeeignet für öffentliches GitHub-Release,
      PolySchnack ist kommerziell)
- [x] Alternative recherchiert: **VoxPopuli-de** (facebook/voxpopuli, CC0-1.0,
      Public Domain, nicht gated) — User-Entscheidung 26.08. nach Recherche
      (KALAKA/KALLIS nicht frei, ALLIES französisch, Fischbach-2024 nur DID)
- [x] VoxPopuli-de-Test-Split: 1968 Segmente, 123 Sprecher (78 mit ≥8
      Segmenten), 16 kHz, Sprecher-IDs je Segment als GT

## 1. Testset bauen (VoxPopuli-de-Mixe) — ERLEDIGT 26.08.

- [x] `benchmarks/diar/build_diar_testset.py`: 20 Calls, 142 GT-Segmente,
      2–4 Sprecher/Call, 32–102 s, deterministisch (Seed 42), exakte GT
      (Parlamentsrede-Segmente aneinandergereiht mit Pausen)
- [x] Assets unter `benchmarks/diar/assets/v1/` (diar-manifest.json, SHA256SUMS,
      20 WAVs 16 kHz mono, Lizenz CC0)
- [x] Held-out: entfällt — Testset ist vollständig öffentlich (CC0)
- [x] `build_diar_package` (lokale Quelle `DIAR_PACKAGE_LOCAL_DIR`, Fallback
      `DIAR_PACKAGE_URL` GitHub-Release) + `diar_package_sha256`
- [x] Endpunkte: `/api/benchmark/diarpackage` + `/diarpackage/sha256` +
      `/diarsamples` + `/diaraudio/{id}` + `/diarpreview/{id}`

## 2. Metriken + Backend — ERLEDIGT 26.08.

- [x] `benchmarks/diar/diar_metrics.py`: DER (optimale Sprecher-Zuordnung,
      brute force ≤4 Sprecher), Jaccard je Segment, Sprecherzahl-Fehler, RTF
      — Selbsttest grün, Verifikation gegen echtes Testset (GT=0, verrauscht
      0.017–0.382)
- [x] `_diar_summary(runs_dir)` in benchmark_service.py (kind="diar"):
      DER/Jaccard/Sprecherzahl/RTF je Methode + testset_version
- [x] latest.json: `diar`-Sektion (analog `vad`), on-the-fly nachgerüstet
      (apply_submission + latest_results)
- [x] Submit-Route: kind="diar" validiert gegen `diar_models.yaml`
      (crispr-diar-foxnose/pyannote/vad-turns) — Literal + SampleResultRow
      erweitert
- [x] Bugfix: ASR-Pool ignoriert jetzt alle non-ASR-Runs (Diar-Runs ohne `wer`
      erzeugten vorher leere Pool-Einträge → ZeroDivisionError)

## 3. Runner + Selfservice — ERLEDIGT 26.08.

- [x] `benchmarks/diar/diar_run.py`: Audio → Segment-Liste je Methode
      (crispr-diar-API, response_format=diarized_json, identisch zu
      webapp/app/diarize.py inkl. Change-126-Embedder-Fix)
- [x] `benchmarks/diar/diar_selfservice.py`: Package → messen → submit
      (HMAC, kind="diar", Exit-Codes wie vad_selfservice)
- [x] `benchmarks/diar/README.md`

## 4. GUI: Diar-Tab füllen — ERLEDIGT 26.08.

- [x] `DiarResultsTable` (DER↓/Jaccard/Sprecherzahl/RTF je Methode) +
      Empty-State mit Testset-Erklärung
- [x] Diar-Samples anhörbar (Audio-Player + WAV-Download) —
      `BenchmarkDiarSamples`, App.tsx lädt `/diarsamples`
- [x] SuiteExplainer.diar aktualisiert (VoxPopuli-Testset, CC0, statt „geplant“)

## 5. Tests + Gate — ERLEDIGT 26.08.

- [x] Backend: 4 Diar-Submit-Tests (Pool-Separation, SHA-Endpoint, unbekannte
      Methode 422, pyannote/vad-turns erlaubt) — 25/25 Submit-Router +
      36/36 Benchmark-Router grün
- [x] Frontend: 4 Diar-Tests (Empty-State, Tabellen-Values, Samples, WAV-Links)
      — 53/53 BenchmarkPage grün
- [x] tsc --noEmit sauber, npm run build ok

## 6. Commit, Push, CI — OFFEN

- [ ] Commit, Push, CI-Watch
- [ ] GitHub-Release `diar-set-v1` (diar-testset-v1-public.tar.gz) in
      tilllt/polyschnack-benchmark-data (nach CI-Grün)
