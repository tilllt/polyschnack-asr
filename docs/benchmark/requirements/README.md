# Backend-Ressourcen-Requirements (ASR-Benchmark)

Eine Datei je Backend mit den **minimalen Ressourcen** (GPU/VRAM, Disk, RAM)
und den belegten Werten aus Produktion/Benchmark. Quelle der Backend-
Definitionen (Images, onstart, Ports): `start_timing_vast.py` / `backend_benchmark_full.py`
(Betreiber-Host `/opt/data/scripts/`). Erstellt 2026-08-20 (Change 033).

## Übersicht

| Backend | GPU-Klasse | VRAM | Miet-Disk | Modell (Download) | Image | Status 207er |
|---|---|---|---|---|---|---|
| ps-pk-onnx | RTX 3060/4070 | 12 GB | ≥ 30 GB | im Image (Parakeet-ONNX) | GHCR | WER 0,1615 |
| crispr-pk-cpp | RTX 3060/4070 | 12 GB | ≥ 30 GB | 0,67 GB GGUF | GHCR | WER 0,1619 |
| crispr-qwen3 | RTX 3060/4070 | 12 GB | ≥ 30 GB | 1,35 + 1,84 GB GGUF | GHCR (privat) | WER 0,2795 |
| crispr-ark | RTX 3060/4070 | 12 GB | ≥ 30 GB | 4,29 GB GGUF | GHCR | fehlgeschlagen (UTF-8) |
| crispr-moonshine-de | RTX 3060/4070 | 12 GB | ≥ 30 GB | 0,04 GB GGUF + Tokenizer | GHCR | WER 0,2683 |
| crispr-canary | RTX 3060/4070 | 12 GB | ≥ 30 GB | 0,61 GB GGUF | GHCR | WER 0,2703 |
| whisper-large-v3 | RTX 3060/4070 | 12 GB | ≥ 30 GB | im Image (faster-whisper, ~3 GB) | Harbor | Lauf 20.08. |
| voxtral-mini-realtime | RTX 3090/4090 | **16 GB+** (24 GB empfohlen) | ≥ 30 GB | 4B-Modell von HF bei Start | Docker Hub vllm | Lauf 20.08. |

## Gemeinsame Basis (Runner, belegt)

- **Miet-Disk:** `DISK_GB = 30`; Angebote mit `disk_space < 25` werden verworfen.
  Belegt 19.08.: 3060-Offers mit 12 GB Disk → Modell-Download 200 % belegt →
  Server-Crash.
- **CUDA/Treiber:** Images basieren auf `nvidia/cuda:12.8`; Hosts mit
  `cuda_max_good < 12.8` werden gefiltert (sonst SIGILL „forward compatibility",
  belegt 18.08.).
- **Region:** nur EU-Angebote (EU_COUNTRIES-Liste im Runner).
- **Preis-Cap:** 0,35 $/h (env `VAST_MAX_PRICE` übersteuerbar).
- **RAM:** Mindestbedarf im Container nicht separat gemessen; beobachtete
  Miet-Hosts: 128–257 GB Host-RAM (RTX-3060-Angebote). Modellgröße (s. je
  Backend) ist die dominante Komponente.
- **Startzeit:** je Backend `slow_start`-Flag (whisper/voxtral = großes Modell,
  Port bleibt beim Laden lange zu — kein Crash-Alarm).

## Beleg-Methodik (keine Schätzwerte)

- **Modellgrößen:** `HEAD` auf HuggingFace-`resolve/main` (Content-Length),
  2026-08-20.
- **Image-Größen:** Harbor-API (whisper 2,51 GB) bzw. Docker-Hub-API
  (vllm 10,53 GB); GHCR-Größen nicht öffentlich abrufbar (403/404 anonym).
- **VRAM-Klasse:** erfolgreiche Läufe auf RTX 3060 (12 GB) bzw. RTX 3090
  (24 GB, voxtral-Schnelltest 19.08.); voxtral-VRAM-Bedarf laut Modellkarte
  „16 GB+" (Kommentar im Runner, belegt 19.08.).
- **WER/RTF/Kosten:** Ergebnis-JSONs unter `/opt/data/vast-benchmarks/logs/`.
