# Change 029 — Design

## Images (Vorlage: ark-asr-cpp/Dockerfile, CrispASR-Hybrid Weg 1)

Beide Images basieren auf `nvidia/cuda:12.8.0-runtime-ubuntu24.04` und
laden das **pre-compiled CrispASR-Release-Binary v0.8.29** (CUDA + CPU,
Hybrid-Wrapper `crispasr` wählt zur Laufzeit via libcuda.so.1-Check).
Kein Eigen-Build von CrispASR → kurze CI-Buildzeit (Download-only).

| Backend | Ordner | Image | Port | CrispASR-Flag | GGUF-Default |
|---|---|---|---|---|---|
| crispr-voxtral | `voxtral-crisp/` | `polyschnack-asr-voxtral` | 5100 | `--backend voxtral4b` | `Voxtral-Mini-4B-Realtime-2602-Q8_0.gguf` (handy-computer, 4,7 GB) |
| crispr-whisper | `whisper-crisp/` | `polyschnack-asr-whisper-crisp` | 5101 | `--backend whisper` | `ggml-large-v3-turbo-q5_0.bin` (ggerganov/whisper.cpp) |

- Modelle liegen NICHT im Image (Volumen `./DATA/models:/models:ro` wie
  ark/canary/moonshine); `backends.yaml model_files` liefert die
  Download-URLs für `polyschnack-manage.sh models`.
- `CRISPASR_EXTRA_ARGS` (Server-Flag): `--punc-model fullstop
  --truecase-model lstm` (identisch zu den anderen CrispASR-Backends).

## Server-Modus

`crispasr --server [--backend X] -m "$MODEL" --host 0.0.0.0 --port <port>`
— OpenAI-kompatibler Endpoint (`/v1/audio/transcriptions`), Health unter
`/health` (identisch zu ark/canary/moonshine; der bestehende Adapter
`app.asr_client.adapters.crisp_asr_http:CrispAsrHttpClient` funktioniert
unverändert).

## CI

- Zwei neue Jobs `build-voxtral` + `build-whisper-crisp` (Muster
  `build-canary`: ci-tools-Image, `ci_smart_build.sh`, `needs: test-webapp`,
  timeout 30 min — Download-only-Builds).
- `mirror-github`: needs-Liste erweitern.
- `mirror-ghcr`: Image-Liste erweitern um `-voxtral`, `-whisper-crisp`.

## Registry / Webapp

- `compose.backends.yml`: 2 neue Profile (5100/5101, memory 8G/4G,
  healthcheck `/health`, start_period 120 s/90 s).
- `webapp/app/backends.yaml`: 2 neue Blöcke (Adapter CrispAsrHttpClient,
  capabilities word_timestamps true, languages de/en, device gpu+cpu).
- `start_timing_vast.py` (lokal, Benchmark-Skripte): BACKENDS-Einträge für
  spätere vast-Benchmarks werden NACH Abnahme ergänzt (nicht Teil des
  Repo-Commits).

## Verifikation

- YAML-Validierung (compose.backends.yml, backends.yaml) lokal.
- CI-Pipeline grün (build-Jobs + mirror), Images auf Harbor verifizieren
  (`docker pull`/API-Tag-Check).
- Optional: CrispASR-Binary-Smoke-Test auf vast-Instanz (voxtral4b + Whisper
  transkribieren je 1 deutsches Sample) vor/nach CI.
