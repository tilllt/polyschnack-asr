# Change 081 — Tasks

## 1. Provenienz im Dateinamen (Skripte) — UMGESETZT

- [x] `regenerate_tts_vibevoice.py`: Dateinamen mit Sprecher-Suffix
      (`{pool}_{i:03d}_{voice}.wav`), resolve_source toleriert Alt+Namen
- [x] `regenerate_tts_piper.py`: `{pool}_{i:03d}_thorsten.wav`
- [x] `prepare_cv_real.py`: `_tts_src()`-Helper (beide Namensarten), source_path
      mit Sprecher-Suffix
- [x] `build_testset_v3.py`: Kommentar + Glob matcht beide Namensarten
- [x] py_compile OK + resolve_source-Smoke-Test bestanden

## 2. ASR-Suite-Package v2 (Ramona raus)

- [ ] `build_suite_package.py` mit SUITE_VERSION=2 ausführen (Quelle = aktuelles
      Manifest + aktuelle categories/ — bereits VibeVoice)
- [ ] SHA256-Verifikation: zahlen_002 in v2 == 1d729b57 (aktuelle Quelle)
- [ ] Import in benchmark_data_pkg (v2 installiert, v1 als Altlast)
- [ ] Webapp-Test: `/api/benchmark/meta` → version 2

## 3. VAD-Testset-V4 (Ramona raus)

- [ ] `build_testset_v3.py` (public-Split) mit aktuellen tts-Quellen ausführen
- [ ] assemble_release_zip.py → vad-benchmark-v4-public.zip + SHA256
- [ ] Verify: de_01-Ableitung == aktuelle VibeVoice-Quelle (nicht Ramona)

## 4. Tests + Gate

- [ ] Backend-Tests grün (benchmark_service nutzt neues Paket)
- [ ] Frontend-Tests + build

## 5. Commit, Push, CI

- [ ] Commit (pk-asr: build-Skripte/Provenienz + OpenSpec), Push, CI-Watch
- [ ] Benchmark-Repo (polyschnack-benchmark): Regen-Skripte committen
