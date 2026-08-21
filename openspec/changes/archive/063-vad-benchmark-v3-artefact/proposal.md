# Change 063 — VAD-Benchmark V3: offizielles Testset-Artefakt + FSMN-VAD

**Status:** Archived (abgeschlossen, 2026-08-21) · **Datum:** 2026-08-21

## Problem

- Das V2-Testset (Change 060/062) wird lokal generiert (gitignored Assets)
  — nicht reproduzierbar für externe Läufer (vast-Container, andere Rechner).
- DEMAND-modifizierte Basis-Samples (SNR-Mix) sind erst teilweise drin
  (nur 6 von 12 Samples, erst 3 Stufen).
- FSMN-VAD (Alibaba FunASR, **Apache-2.0** — einzige lizenz-saubere echte
  Alternative zu Silero) fehlt als Kandidat.

## Ziel

1. **V3-Testset** als offizielles Artefakt auf GitHub-Release
   (`tilllt/vad-benchmark-data`, Versionen + SHA256): Basis-Samples
   (DE-Synth mit Stille-Insertion) + DEMAND-modifizierte Varianten
   (SNR 0/5/10 dB auf ALLEN Basis-Samples) + Babble + TEN + Noise + Musik,
   deterministisch generiert, GT als JSON. Benchmark + Container laden das
   Artefakt (Fallback: lokale Generierung).
2. **FSMN-VAD** als Engine (Apache-2.0, multilingual inkl. DE, ONNX
   verfügbar) — Potential-Check + Benchmark-Einbindung.

## Umsetzung (Skizze)

1. **Testset-Builder** (`benchmarks/vad/build_testset_v3.py`): generiert
   deterministisch (Seeds fest) das V3-Testset + `testset.json` (GT),
   packt `vad-testset-v3.tar.gz` (WAVs + JSON), berechnet SHA256.
2. **GitHub-Release**: Repo `tilllt/vad-benchmark-data` (public) +
   Release `v3` mit Artefakt; Download-URL + SHA256 im Benchmark-README
   und in `run_benchmark.py` (Cache `assets/v3/`, Fallback lokal).
3. **FSMN-VAD-Engine** in `vad_engines.py` (funasr-ONNX oder torch,
   .venv-torch), Lizenz Apache-2.0 → produktiv nutzbar.
4. **run_benchmark.py V3**: Artefakt-Download (oder Generierung), alle
   Engines (silero, ten_vad, webrtc, humaware, speechbrain, energy, fsmn).
5. Doku: component-decisions.md (FSMN-Ergebnis), README (Download/Repro).

## Referenzen

- FSMN-VAD: Alibaba FunASR, Apache-2.0, 10-ms-Frames, streaming,
  multilingual (inkl. DE), ONNX-Export vorhanden
- Testset-Komposition V2: benchmarks/vad/run_benchmark.py (build_testset)
