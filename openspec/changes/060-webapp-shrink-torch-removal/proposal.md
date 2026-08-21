# Change 060 — Webapp-Shrink: torch raus (VAD auf onnxruntime) + VAD-Benchmark

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

Das Webapp-Image ist auf **3,06 GB (komprimiert)** gewachsen. Größenanalyse
(Registry-Manifest `ghcr.io/tilllt/polyschnack-asr-webapp:latest`, 12 Layer):

- **Layer `uv sync` = 2,8 GB komprimiert** (Inhalt verifiziert: `/.venv` =
  4,9 GB unkomprimiert, `/.cache` 37 MB) — Rest (Debian-Basis + Python +
  uv + ffmpeg + nodejs + yt-dlp + app) ≈ 260 MB komprimiert.
- **Ursache:** `pyproject.toml` enthält seit **2026-07-25** (Commit `55b46ef`,
  „Silero VAD silence trimming") `silero-vad>=6.0.0`. Das PyPI-Paket
  **silero-vad 6.2.1** deklariert **`torch` 2.13.0 + `torchaudio` 2.11.0 als
  Pflicht-Dependencies** (uv.lock) — `uv sync` installiert CPU-torch mit.
  Der Dockerfile-Kommentar „Kein CUDA-torch mehr in der Webapp (~2,5–3 GB
  kleiner)" ist damit falsch (Regression).
- **torch wird nicht gebraucht:** `app/vad.py` lädt das Modell mit
  `load_silero_vad(onnx=True)` (ONNX-Pfad); `onnxruntime` ist nicht mal im
  Lock. Verifiziert: silero-vad importiert torch bereits beim Modul-Import
  (`utils_vad.py` Zeile 1) → `--no-deps` ohne Code-Änderung unmöglich.
- **Nutzungsumfang VAD:** nur Trim (3 Aufrufe in `service.py`),
  `detect_speech_regions` wird von keinem App-Code aufgerufen.

## Ziel

1. Webapp-Image von ~3,06 GB auf **~0,4–0,5 GB komprimiert** reduzieren
   (torch/torchaudio/silero-vad raus, `onnxruntime` rein).
2. VAD-Trim bleibt funktional: **Silero-VAD-Modell direkt via onnxruntime**
   (gleiches Modell `silero_vad.onnx`, MIT, ~2 MB), gleiche API
   (`trim_silence_with_offset`, `detect_speech_regions`), gleiche
   Parameter (threshold 0.5, min_silence 400 ms, pad 120 ms).
3. **VAD-Benchmark** als Evidenzbasis für die Modellwahl (PolySchnack-Prinzip:
   nie raten): Silero-onnx vs. TEN VAD (Agora, open) vs. WebRTC/Energy-Baseline
   vs. CrispASR-nativ (`--vad`) auf eigenen DE-Samples mit deterministischer
   Stille-Insertion (exakte Ground Truth) + DEMAND-Noise-FP-Test
   (CC-BY-4.0). Entscheidung mit Quellen in `docs/component-decisions.md`.

## Umsetzung

1. **`webapp/app/vad.py`** auf onnxruntime umstellen: Modell-Download
   `silero_vad.onnx` (snakers4 GitHub, MIT) nach `DATA_DIR/models/`, Session
   + numpy-Inferenz (512er-Chunks @ 16 kHz), Speech-Region-Logik
   (threshold/min_silence/pad) als pure Funktionen (testbar ohne Modell).
2. **`webapp/pyproject.toml`:** `silero-vad` raus, `onnxruntime>=1.18` rein;
   `uv.lock` neu auflösen.
3. **Dockerfile-Kommentar** korrigieren (torch-frei stimmt wieder).
4. **Tests:** `test_vad_trim_offset.py` grün halten (Session gemockt),
   neue Tests für die pure Region-/Trim-Logik.
5. **VAD-Benchmark** unter `benchmarks/vad/`: Testset-Generator
   (Stille-Insertion in `polyschnack-benchmark/benchmark/data/fqs/` + `tts/`),
   Engines (silero_onnx, ten_vad, energy, webrtc, crispasr falls Binary
   verfügbar), Metriken: Boundary-Fehler (ms), Region-F1, FP auf Noise, RTF.
6. Ergebnisse in `docs/component-decisions.md` (mit Quellen).
7. Folge-Change 061 (Proposal): ASR-Benchmark um DEMAND-Noise-Mix erweitern
   (kontrollierte SNR-Stufen) — separate Umsetzung.

## Referenzen

- Größenanalyse: GHCR-Manifest + Layer-9-Inhalt (2026-08-21)
- silero-vad 6.2.1 → torch/torchaudio: `webapp/uv.lock`
- VAD-Optionen: Picovoice-Benchmark (ROC, TPR@FPR),
  [CrispASR `--vad` (Silero-GGUF 885 KB)](https://github.com/CrispStrobe/CrispASR),
  [TEN VAD (Agora, open)](https://github.com/TEN-framework/ten-vad),
  [DEMAND (CC-BY-4.0 auf HF)](https://huggingface.co/datasets/voice-biomarkers/DEMAND-acoustic-noise)
