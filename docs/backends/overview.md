# Backend-Übersicht

PolySchnack unterstützt **mehrere ASR-Engines** — lokal als eigene Container
und optional Remote über OpenAI-kompatible APIs. Die **Registry**
(`webapp/app/backends.yaml`) ist die Single Source of Truth: Name, Port,
Modell-Downloads, Capabilities, Adapter. Die GUI wählt das Backend **pro
Job** (Default: `POLYSCHNACK_DEFAULT_BACKEND` bzw. Admin-GUI); `ASR_BACKEND`
ist nur der Fallback für direkte API-Aufrufe.

## Lokale Backends (eigene Container)

| Backend | Profil | Port | Beschreibung |
|---------|--------|------|-------------|
| **Parakeet (Python/ONNX)** | *(Default)* | 5092 | Original-Modell von NVIDIA, 0,6B. Hybrid GPU/CPU, auto-detect. Einziges Backend mit Live-Streaming, Async-Jobs und Noise-Reduction. |
| **parakeet.cpp (CrispASR)** | `crispr-pk-cpp` | 5093 | Gleiches Modell in C++ — schneller, ~700 MB quantisiert. Native Interpunktion + deutsches Truecasing. |
| **Qwen3-ASR (CrispASR)** | `crispr-qwen3` | 5094 | Alibaba, 30 Sprachen, Word-Timestamps via ForcedAligner (~3 GB beide Modelle). |
| **ARK-ASR (CrispASR)** | `crispr-ark` | 5095 | State-of-the-Art auf dem HF ASR Leaderboard, 3B Parameter. |
| **Moonshine-DE (CrispASR)** | `crispr-moonshine-de` | 5096 | Kompaktes deutsches Spezialmodell (61,5M, ~39 MB GGUF). ⚠️ Lizenz CC-BY-NC-SA-4.0 (nicht-kommerziell). |
| **Canary (CrispASR)** | `crispr-canary` | 5097 | NVIDIA Canary 1B v2 — multilingual (EN/DE/FR/ES). |
| **Voxtral (CrispASR)** | `crispr-voxtral` | 5100 | Mistral Voxtral-Mini-4B-Realtime (Q8_0, offizielle cstr-GGUF). |
| **Whisper (CrispASR)** | `crispr-whisper` | 5101 | OpenAI Whisper large-v3-turbo (ggml q5_0) über CrispASR. |

Alle lokalen Backends sind **hybrid** (GPU + CPU), nutzen die gemeinsamen
Modelle in `./DATA/models` und native Interpunktion + deutsches Truecasing
(`--punc-model fullstop --truecase-model lstm`).

## Remote-Backends (kein Container)

| Backend | Typ | Beschreibung |
|---|---|---|
| **whisper-large-v3** | remote | faster-whisper large-v3 (int8_float16); URL/Key via `WHISPER_LARGE_V3_URL` / `WHISPER_LARGE_V3_API_KEY` |
| **voxtral-mini-realtime** | remote | Mistral Voxtral-Mini-4B-Realtime (vLLM, bf16); URL/Key via `VOXTRAL_MINI_REALTIME_URL` / `VOXTRAL_MINI_REALTIME_API_KEY` |

Remote-Backends sprechen OpenAI-kompatibles `POST {base_url}/audio/transcriptions`
(Bearer-Auth). Weitere auskommentierte Beispiele (OpenAI/Groq) liegen in
`backends.yaml` — aktivieren: Block einkommentieren, API-Key als Env an den
webapp-Container, Stack neu starten. **Nie Keys ins YAML/Repo.**

## Adapter-URLs

Jeder Adapter hat **seine eigene URL-Env** — nie `ASR_URL` für andere
Backends verwenden (das ist der ONNX-Container!):

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASR_BACKEND` | `ps-pk-onnx` | Fallback-Adapter für direkte API-Aufrufe |
| `POLYSCHNACK_DEFAULT_BACKEND` | `ps-pk-onnx` | GUI-Default für neue Jobs (per Admin-GUI änderbar) |
| `ASR_URL` | `http://ps-pk-onnx:5092` | ONNX-Container |
| `CRISPR_PK_CPP_URL` | `http://crispr-pk-cpp:5093` | parakeet.cpp |
| `CRISPR_QWEN3_URL` | `http://crispr-qwen3:5094` | Qwen3-ASR |
| `CRISPR_ARK_URL` | `http://crispr-ark:5095` | ARK-ASR |
| `CRISPR_MOONSHINE_DE_URL` | `http://crispr-moonshine-de:5096` | Moonshine-DE |
| `CRISPR_CANARY_URL` | `http://crispr-canary:5097` | Canary |
| `CRISPR_VOXTRAL_URL` | `http://crispr-voxtral:5100` | Voxtral |
| `CRISPR_WHISPER_URL` | `http://crispr-whisper:5101` | Whisper |
| `CRISP_ALIGN_URL` | `http://crispr-align:5099` | Forced-Aligner |

Die `*_URL`-Variablen sind **nur Overrides** für Spezialfälle — im Normalfall
weglassen (URLs werden automatisch aus Service-Name + Port abgeleitet).

## Neues Backend einbauen (3 Schritte)

1. **Registry:** YAML-Block in `webapp/app/backends.yaml` (Name,
   `compose_profile`, Port, `model_files` mit URLs, Capabilities, Adapter).
2. **Container:** Service in `compose.backends.yml` (Image, Volumes, Port,
   Healthcheck, Profil).
3. **Auswahl:** Name in `POLYSCHNACK_BACKENDS` (`.env`), dann
   `./polyschnack-manage.sh models` + `start`.

Kein Skript-Eingriff nötig. Details zum Zusammenspiel:
[Compose-Referenz](../compose.md).
