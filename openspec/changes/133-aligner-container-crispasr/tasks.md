# Change 133 — Tasks

## 1. Voruntersuchung (erledigt, 2026-08-26)

- [x] CrispASR-Qwen3FA-Pfad im Code verifiziert (`crispasr_aligner.cpp`,
      `AlignerType::Qwen3FA`, Dispatch am Dateinamen "forced-aligner")
- [x] OpenVoiceOS-GGUF: Mel-Tensoren fehlen → `mel failed` (hard error)
- [x] `cstr/qwen3-forced-aligner-0.6b-GGUF` (HF) geladen: f16 + q8_0
- [x] Beweis: CrispASR + cstr-GGUF = qwen3-asr-cli verhaltensgleich
      (POC 36/36 bitweise identisch; 90-s-Kollaps identisch — Modelleigenschaft)
- [x] q8_0 vs f16: 0 Zeit-Diffs → q8_0 für Container (986 MB)

## 2. aligner-service/Dockerfile auf CrispASR-Basis

- [ ] Builder: CrispASR-Checkout + Build (CPU oder CUDA — Entscheidung:
      qwen3-FA lief im Test auf CPU in 77 s für 90 s Audio; CUDA-Build
      analog diar-service für GPU-Beschleunigung, Fallback CPU)
- [ ] Runtime: `nvidia/cuda:12.8.0-runtime-ubuntu24.04` + ffmpeg + python3
      (wie bisher), CrispASR-Binary + ggml-Libs kopieren
- [ ] `ENV`-Defaults: `CRISPASR_BIN=/usr/local/bin/crispasr`,
      Modell-Pfade unter `/models/`:
      - `ALIGNER_MODEL_QWEN3=/models/qwen3-forced-aligner-0.6b-q8_0.gguf`
      - `ALIGNER_MODEL_TADA=/models/tada-tts-1b-q4_k.gguf`
      - `ALIGNER_MODEL_WAV2VEC2=/models/wav2vec2-large-xlsr-53-german-q4_k.gguf`
- [ ] Entrypoint: Modell-Downloads bei Bedarf (Volume :rw, wie bisher)
- [ ] Port 5099 bleibt

## 3. aligner_server.py: method-Dispatch

- [ ] `_run_aligner(method, ...)` statt `_run_aligner(cli, model, ...)`:
      Dispatch-Tabelle:
      - `qwen3`: `crispasr --align-only -am <qwen3> --ref-text <text>`
      - `tada`: `crispasr --align --voice <wav> --ref-text <text> --source-lang <lang>`
        (Companion-Modelle neben tada-tts-1b, wie in
        `aligner-benchmark-3way.md` dokumentiert)
      - `wav2vec2`: `crispasr --align-only -am <wav2vec2> --ref-text <text>`
      - Default: `qwen3`
- [ ] `do_POST`: Form-Feld `method` (Default `qwen3`), unbekannte Methode → 422
- [ ] Output-Format: `--align-output <json>` (CrispASR-JSON), `_parse_alignment`
      bleibt tolerant
- [ ] Status-Endpunkt: zeigt Methode + Modell im Job-Label
- [ ] `main()`: Args umbauen (`--crispasr-bin`, Modell-Pfade aus Env,
      `--host/--port` bleiben)

## 4. aligner_client.py (Webapp)

- [ ] `align(audio_bytes, text, lang="de", method="qwen3")` — method als
      Form-Feld mitgeben
- [ ] Default `qwen3` = heutiges Verhalten, kein Breaking Change
- [ ] Fehlerfall: unbekannte Methode → verständliche Exception

## 5. Tests

- [ ] `webapp/tests/`: Dispatch-Tests (mock CLI, prüfe Argument-Listen je
      Methode), Default-Test, 422 bei unbekannter Methode
- [ ] Volle Backend-Suite grün
- [ ] Frontend-Build (tsc/vite) grün — nur falls UI-Texte geändert

## 6. Integration Benchmark (Hinweis, nicht Teil dieses Changes)

- [ ] `benchmarks/aligner/run_aligner.py` auf HTTP-API umstellen
      (Folge-Change oder im Rahmen von 132-Fertigstellung — Abhängigkeit:
      Server läuft im Container)

## 7. Commit, Push, CI

- [ ] OpenSpec-Change committet
- [ ] Push GitLab, CI grün, Harbor-Image deploybereit
- [ ] User-Deploy-Roadmap mitteilen (compose pull aligner + up)
