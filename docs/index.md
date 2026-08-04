# PolySchnack — Multi-Backend Speech-to-Text

**OpenAI-kompatible Spracherkennung mit wählbaren ASR-Backends** — von lokalen
ggml/C++-Engines bis zur Cloud-API. Mit Web UI, Live-Transkription,
Word-Timestamps, Sprechererkennung (Diarization), OIDC-Workspaces und einem
öffentlichen **Benchmark** (WER/€-Vergleich der Backends).

Ein Befehl startet den kompletten Stack (CPU überall, GPU via Overlay) —
ohne Code, ohne Lock-in: Du wechselst das Erkennungsmodell per Env-Variable
oder per Admin-GUI, die Qualität bleibt messbar dank integriertem Benchmark.

---

## Kernbotschaft

PolySchnack ist aus **[NVIDIA Parakeet ASR](https://github.com/nvidia/parakeet)**
entstanden und wurde zu einer **Multi-Backend-Plattform** erweitert: Ein
einheitlicher OpenAI-kompatibler Endpunkt, dahinter wählbar Parakeet
(Python/ONNX oder C++), Qwen3-ASR, ARK-ASR, Moonshine-DE und Canary — jedes
mit eigener Stärke (Geschwindigkeit, Genauigkeit, Sprachen, Ressourcen).

| | |
|---|---|
| **6 ASR-Backends, ein Endpunkt** | OpenAI-kompatible API — Drop-in für `openai.Audio.transcriptions.create()`. Backend-Wechsel per Env-Variable oder Admin-GUI. |
| **Web UI mit Wellenform** | WaveSurfer-Player mit Zoom (1×–50×), Segment-Editor, Bereichs-Transkription, Export (SRT/VTT/TXT), Live-Preview per SSE. |
| **Word-Timestamps** | Echte Word-Level-Timestamps via Forced Aligner (Qwen3) oder modell-inhärent (Parakeet) — klickbare Wörter. |
| **Diarization** | Sprechererkennung im eigenen CrispASR-Container — kein pyannote/CUDA-torch in der Webapp, hybrid (GPU/CPU). |
| **Hybrid GPU/CPU** | Jeder Service ist EIN Image für GPU UND CPU — ohne Overlay läuft alles auf CPU, mit `compose.gpu.yml` auf der GPU. |
| **Öffentlicher Benchmark** | 2-Achsen-Test-Set (Kanal × Inhalt), hörbare Samples, WER/€-Vergleich. |
| **OIDC-Workspaces** | Ohne Login: Shared Space mit Auto-Retention. Mit Login: private Workspaces + Admin-Bereich. |

## Schnelleinstieg

```bash
git clone <dein-repo-url>
cd polyschnack

# CPU (läuft überall):
docker compose up -d

# GPU (NVIDIA Container Toolkit nötig):
docker compose -f compose.yml -f compose.gpu.yml up -d
```

- **Web UI:** http://localhost:8088
- **ASR API (direkt):** http://localhost:5092

→ Weiter: [Quickstart](quickstart.md) · [Backends](backends/overview.md) ·
[Benchmark](benchmark/index.md)

## Danksagung

Das Projekt startete als Fork von
[istupakov/parakeet-tdt](https://github.com/istupakov/parakeet-tdt) (NVIDIA
Parakeet TDT 0.6B v3) und dessen WebUI. Seitdem kamen hinzu:
Multi-Backend-Adapter, OIDC-Auth, Diarization, Sprachauswahl,
Segment-Editor, WaveSurfer-Integration und eine modulare
C++-Backend-Architektur.
