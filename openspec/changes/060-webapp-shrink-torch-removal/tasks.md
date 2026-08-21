# Tasks — Change 060 (Webapp-Shrink + VAD-Benchmark)

## Shrink (torch raus)

- [x] `app/vad.py`: onnxruntime-Implementierung (Modell-Download nach
      `DATA_DIR/models/silero_vad.onnx`, Session, numpy-Inferenz,
      pure Region-/Trim-Funktionen) — inkl. stateful-Forward + 64er-Kontext
      (gegen offizielle utils_vad.py verifiziert)
- [x] `pyproject.toml`: `silero-vad` → `onnxruntime>=1.18`; `uv lock` neu
      (torch/torchaudio/triton entfernt)
- [x] Dockerfile-Kommentar korrigieren („torch-frei")
- [x] `test_vad_trim_offset.py` grün (Session gemockt) + 4 neue Tests
      (Region-Logik, Chunking, Fehlerpfade) — 25/25 grün
- [x] Backend-Partialtests (test_vad*, test_model_diagnostics,
      test_access_in_routes) grün; Frontend unberührt
- [~] Image-Größe: Ursache (L9 = 2,8 GB / `/.venv` 4,9 GB, torch) belegt;
      Nachher-Messung erst beim nächsten Image-Build (kein lokaler Docker)

## VAD-Benchmark

- [x] `benchmarks/vad/`: Testset-Generator (Stille-Insertion 2 s/1 s in
      DE-TTS-Samples, exakte GT; TEN-.scv-GT; Noise-FP)
- [x] Engines: silero_onnx (Webapp-Implementierung), ten_vad (sherpa-onnx),
      energy (Baseline); CrispASR-nativ bewusst ausgelassen (Silero-GGUF =
      identische Modellqualität; CLI-VAD an ASR-Modell gekoppelt — für den
      isolierten VAD-Vergleich unverhältnismäßig)
- [x] DEMAND-Noise-FP-Test (Zenodo 16k, Küche + Metro, CC-BY-4.0-Mirror)
- [x] Metriken: Boundary-Fehler (ms), Region-F1, FP-Zeit, RTF (CPU)
- [x] Lauf: 37 Samples → silero_onnx F1 0,963 / 0,0 s FP / RTF 0,025
      (out/results.md + results.json)
- [x] Entscheidung mit Quellen in `docs/component-decisions.md`
      (Silero-onnx; TEN VAD wegen Agora-Lizenzklauseln raus;
      Energy wegen Noise-Anfälligkeit raus; FSMN-VAD als Apache-2.0-Ausweichoption notiert)

## Folge

- [x] Change-061-Proposal: ASR-Benchmark um DEMAND-Noise-Mix (SNR-Stufen)
- [ ] Vollsuite, Commit, Push, CI-Check
