# Change 133: Aligner-Container auf CrispASR-Basis (3 Aligner, 1 Binary)

## Problem

Der `aligner-service`-Container baut `qwen3-asr.cpp` (predict-woo) als
separaten CUDA-Build — eigener llama.cpp/ggml-Submodule-Stand, eigener
Wrapper, nur ein Aligner (qwen3-forced-aligner). TADA und wav2vec2
existieren nur als lokale CLI-Versuche, nicht im Container, nicht für die
Webapp nutzbar. Der Container ist der wartungsintensivste Teil des Stacks:
zwei ggml-Runtimes (CrispASR für ASR/Diar + qwen3-asr.cpp für Align)
laufen parallel, der CUDA-qwen3-Build (llama.cpp#23357-Linker-Fixes,
`CMAKE_CUDA_ARCHITECTURES=86`) ist fragil.

**Gegenprobe (2026-08-26, lokal belegt):** Der CrispASR-Code hat seit
April 2026 einen nativen Qwen3FA-Pfad (`src/crispasr_aligner.cpp`,
`AlignerType::Qwen3FA`, erkennt am Dateinamen "forced-aligner"), aber das
OpenVoiceOS-GGUF (bisher im Container) enthält die zwingend benötigten
Tensoren `audio.mel_filters`/`audio.mel_window` NICHT → `mel failed`.
CrispStrobe bietet auf HuggingFace ein eigenes GGUF mit eingebetteten
Mel-Tensoren an: `cstr/qwen3-forced-aligner-0.6b-GGUF` (f16 1,84 GB,
q8_0 986 MB, q5_0, q4_k; Apache-2.0). Damit läuft der qwen3-FA über
CrispASR mit **bitweise identischen Wortzeiten** zum bisherigen
qwen3-asr-cli (POC 36/36, alle 8 geprüften Wörter identisch; q8_0 =
f16, 0 Zeit-Diffs). Auf dem 90-s-Clip zeigt CrispASR+Qwen3FA dasselbe
Kollaps-Verhalten (87/88 Wörter 0-Dauer, Sentinel schlägt korrekt an) —
der Abbruch ist eine Modelleigenschaft, kein Runtime-Unterschied.

## Ziel

1. **Ein Container, ein Binary, ein Wrapper** für alle 3 Aligner:
   - `method=qwen3` → CrispASR `--align-only -am qwen3-forced-aligner-0.6b-q8_0.gguf`
   - `method=tada` → CrispASR `--align` (TADA: tada-tts-1b + codec + encoder + aligner-de)
   - `method=wav2vec2` → CrispASR `--align-only -am wav2vec2-xlsr-de-q4_k.gguf`
2. **CrispASR als einzige Runtime** im aligner-Container (ersetzt
   qwen3-asr.cpp-CUDA-Build); Modelle im Volume, nicht im Image.
3. **Webapp nutzt denselben Weg** (`aligner_client.py` reicht `method`
   durch, Default `qwen3` = heutiges Verhalten, kein Breaking Change).
4. **Benchmark nutzt denselben Weg** (run_aligner.py → HTTP-API statt
   lokale CLI-Aufrufe, gleiche Metriken).

## Nicht-Ziele

- Kein Wechsel des Webapp-Defaults (Karaoke bleibt qwen3).
- Keine Änderung an TADA/wav2vec2-Modellen oder -Aufrufen (Signaturen
  bleiben, wie in `aligner-benchmark-3way.md` dokumentiert).
- Kein CrispASR-Upstream-Patch für fehlende Mel-Tensoren (Weg A/B aus der
  Recherche: cstr-GGUF ist der saubere Weg ohne C++-Eingriff).
- Kein Deploy (User-Schritt, wie immer).

## Nachweis

- Backend-Suite grün (inkl. neuer Dispatch-Tests: method-Parsing,
  Default `qwen3`, unbekannte Methode → 422, fehlende Datei → 400).
- Frontend-Build (tsc/vite) grün; Webapp-Tests grün.
- Lokaler Smoke-Test: `aligner_server.py` mit allen 3 Methoden gegen
  CrispASR-Binary auf POC-Audio (36 Wörter je Methode, plausible Zeiten).
- CI grün, Harbor-Image deploybereit.
