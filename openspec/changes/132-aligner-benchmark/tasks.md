# Aufgaben — Change 132: Aligner-Benchmark

## 1. Runner-Suite `benchmarks/aligner/`

- [ ] `run_aligner.py` anlegen (analog `benchmarks/vad/run_benchmark.py`):
  - Manifest lesen (`<BENCHMARK_DATA_DIR>/versions/v1/manifest.json`),
    Samples filtern (Quellen cv + tts; `held_out=false` optional),
    optional `--limit N` / `--category X` / `--sources cv,tts`
  - Für jedes Sample + jeden Aligner:
    - Audio als 16-kHz-mono-WAV sicherstellen (ffmpeg, Cache)
    - qwen3: `qwen3-asr-cli -m <model> -f <wav> --align --text <ref> --lang de -o <out.json>`
    - TADA: `crispasr -m tada-1b.gguf --codec-model ... --source-lang de --align --voice <wav> --ref-text <ref>`
    - wav2vec2: `crispasr --align-only -am <wav2vec2-de.gguf> -f <wav> --ref-text <ref>`
  - Ausgabe parsen (qwen3: JSON `{words:[...]}`; CrispASR: `{words:[...]}`) →
    Metriken je Sample (Wortabdeckung, 0-Dauer, Audio-Abdeckung, RTF)
  - Run-JSON schreiben: `results/runs/aligner_<backend>_<ts>.json` mit
    `kind="aligner"`, `manifest_sha256`, `backend`, `rows` (je Sample:
    sample_id, category, quelle, n_ref_words, n_timed, n_zero,
    coverage_pct, audio_coverage_pct, last_end_s, duration_s, rtf,
    delta_ms_median je Aligner-Paar als `cross_delta_ms`)
  - RC != 0 pro Aligner loggen, Lauf nicht abbrechen
- [ ] `README.md` mit Aufruf, Metriken, Modell-Pfaden/-URLs
- [ ] Modell-URLs aus `aligner-benchmark-3way.md`-Referenz übernehmen
  (tada-1b + codec + encoder + aligner-de, wav2vec2-xlsr-de-q4, qwen3-f16)

## 2. Service `benchmark_service.py`

- [ ] `_aligner_summary(runs_dir)` analog `_vad_summary`:
  - kind=="aligner"-Runs mit aktuellem `manifest_sha256` poolen
  - je Backend: n_samples, Wortabdeckung-Mittel (%), Audio-Abdeckung-
    Mittel (%), 0-Dauer-Gesamt, Kreuz-Δ-Median (ms), RTF-Mittel
- [ ] `latest_results()`: `latest["aligner"] = self._aligner_summary(runs_dir)`
  (try/except wie vad)

## 3. Frontend

- [ ] `benchmark.ts`: `AlignerResultRow`-Interface
  (`backend, kind:"aligner", n_samples, word_coverage_mean,
  audio_coverage_mean, zero_duration_total, cross_delta_ms_median, rtf_mean`)
  + `aligner?: AlignerResultRow[]` in `BenchmarkResults`
- [ ] `BenchmarkPage.tsx`: `AlignerResultsTable` + Erklärungsblock
  („Forced-Alignment: Wort-Zeiten für Karaoke — was wird gemessen")
  + Sektion „Forced-Alignment" (zwischen VAD und Preisvergleich)
- [ ] Tests: `BenchmarkPage.test.tsx` (Erklärung sichtbar, Tabelle bei
  aligner-Rows), `benchmark.test.ts` (Parser)
- [ ] `npm run build` grün

## 4. Doku

- [ ] `docs/benchmark/aligner.md` (Methodik, Metriken, Aufruf, Limit.)
- [ ] `docs/benchmark/index.md` Verweis ergänzen

## 5. Verifikation

- [ ] Aligner-Runner auf 6 Stichproben-Samples (3 cv + 3 tts) laufen lassen,
  Runs entstehen, `_aligner_summary` liefert Zeilen
- [ ] Backend-Tests grün (`pytest webapp/tests/ -k benchmark`)
- [ ] Frontend-Tests + Build grün
- [ ] Commit + Push, CI beobachten
