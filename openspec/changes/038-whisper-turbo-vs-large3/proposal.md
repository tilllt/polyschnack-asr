# Change 038: crispr-whisper turbo vs. large-v3 — Benchmark für Namens-Entscheidung

## Problem

Das CrispASR-Whisper-Backend (aktuell `crispr-whisper`) lädt `ggml-large-v3-turbo-q5_0.bin`
— nicht large-v3. Der User fordert konsistente Backend-Benennung:

- **CrispASR-basiert** → `crispr-<modell>` (z. B. `crispr-voxtral-mini`, `crispr-whisper-large-v3`)
- **Selbstgebaut** → `ps-<modell>` (z. B. `ps-whisper-large-v3`, `ps-voxtral-mini-realtime`)

Der aktuelle Name `crispr-whisper` ist unvollständig, und die Suite-Backends
`whisper-large-v3` (faster-whisper) + `voxtral-mini-realtime` (vLLM) tragen
kein Präfix. Für das Whisper-Backend ist die Benennung an die Modellwahl
gekoppelt (turbo vs. non-turbo) — die Qualität/Speed-Differenz ist nicht
geschätzt, sondern muss gemessen werden (Change-021-Prinzip: Werte belegen).

## Lösung

Reproduzierbarer Benchmark auf der 207er-Suite (Methodik wie Change 021/027):
zwei vast-Läufe mit demselben `polyschnack-asr-whisper-crisp`-Image, nur das
Modell unterscheidet sich:

1. `ggml-large-v3-turbo-q5_0.bin` (Status quo, ~1,5 GB)
2. `ggml-large-v3-q5_0.bin` (non-turbo, ~3 GB)

Gemessen wird WER (jiwer, normalisiert) + RTF auf allen 207 Samples. Das
Ergebnis entscheidet die Modellwahl des Backends und damit den Namen.

Danach (Folge-Changes, abhängig von diesem Benchmark):

- Umbenennung nach Schema: `crispr-whisper` → `crispr-whisper-large-v3`
  (oder `crispr-whisper-large-v3-turbo` bei turbo-Sieg),
  `crispr-voxtral` → `crispr-voxtral-mini`,
  `whisper-large-v3` → `ps-whisper-large-v3`,
  `voxtral-mini-realtime` → `ps-voxtral-mini-realtime`
- backends.yaml, compose.backends.yml (Service-Namen/Profile/container_name),
  benchmark_service.py, openai_compat_http.py-Env-Namen, Tests, Docs
- Bereits submittete Suite-Results (Version 2) mit alten Namen: neu submitten
  oder als Historie belassen — Entscheidung nach Benchmark

## Tasks

- [ ] BACKENDS-Einträge in `start_timing_vast.py`: `crispr-whisper-turbo` +
  `crispr-whisper-large-v3` (Image polyschnack-asr-whisper-crisp, onstart
  lädt das jeweilige GGUF, Server `crispasr --server --backend whisper`)
- [ ] Benchmark-Lauf 1: turbo (frische vast-Instanz, 207 Samples, WER+RTF)
- [ ] Benchmark-Lauf 2: large-v3 non-turbo (identische Methodik)
- [ ] Ergebnis-Tabelle: WER/RTF/Kosten, Entscheidung Modell + Name
- [ ] Umbenennung nach Entscheidung (backends.yaml, compose, Code, Tests, Docs)
- [ ] Suite-Results mit neuen Namen (Re-Submit-Strategie)
