# Backend-Übersicht

PolySchnack unterstützt **mehrere ASR-Engines**. Du wechselst einfach per
Env-Variable — kein Code nötig.

| Backend | Profil | CLI-Name | Beschreibung |
|---------|--------|----------|-------------|
| **Parakeet (Python/ONNX)** | *(Default)* | `pk-python` | Das Original-Modell von NVIDIA, 0,6B Parameter. Hybrid: GPU (CUDA) oder CPU (INT8), auto-detect. |
| **parakeet.cpp (ggml/C++)** | `--profile cpp` | `pk-cpp` | Gleiches Modell, aber in C++ — schneller und schlanker (~700 MB quantisiert). Native Interpunktion + deutsches Truecasing. |
| **Qwen3-ASR (ggml/C++)** | `--profile qwen3` | `qwen3-asr` | Neuestes ASR-Modell von Alibaba, 30 Sprachen, **Word-Timestamps** via ForcedAligner (~3 GB beide Modelle). |
| **ARK-ASR (ggml/C++)** | `--profile ark` | `ark-asr` | State-of-the-Art auf dem HF ASR Leaderboard, 3B Parameter, Whisper-Encoder + Qwen2.5-Decoder. |
| **Moonshine-DE (ggml/C++)** | `--profile moonshine` | `moonshine-de` | Kompaktes deutsches Spezialmodell (61,5M Parameter, 6,9 % WER auf CV22-de, ~39 MB GGUF). ⚠️ Lizenz CC-BY-NC-SA-4.0 (nicht-kommerziell). |
| **Canary (ggml/C++)** | `--profile canary` | `canary-asr` | NVIDIA Canary 1B v2 — multilingual (EN/DE/FR/ES). |
| **Voxtral (voxtral.cpp)** | *(geplant)* | `voxtral` | Mistral AI — Speech-to-Text, 4B Parameter, natives Streaming (1 Token je 80-ms-Audioframe). **Noch nicht gebaut** — Block in `compose.backends.yml` auskommentiert. |

## Adapter-URLs

Jeder Adapter hat **seine eigene URL-Env** — nie `ASR_URL` für andere
Backends verwenden (das ist der ONNX-pk-python-Container!):

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASR_BACKEND` | `pk-python` | Adapter-Auswahl (`pk-python`, `pk-cpp`, `qwen3-asr`, `ark-asr`, `moonshine-de`, `canary-asr`) |
| `ASR_URL` | `http://asr:5092` | URL des ONNX-pk-python-Containers |
| `CPP_URL` | `http://polyschnack-cpp:8080` | URL des pk-cpp-Containers (CrispASR parakeet) |
| `QWEN3_URL` | `http://qwen3-asr:8080` | URL des Qwen3-ASR-Containers |
| `CRISPASR_URL` | `http://ark-asr:8080` | URL des ARK-ASR-Containers (CrispASR) |
| `MOONSHINE_URL` | `http://polyschnack-moonshine-de:8080` | URL des Moonshine-DE-Containers |
| `CANARY_URL` | `http://polyschnack-canary:8080` | URL des Canary-Containers |

!!! warning "Adapter-Auswahl nie vergessen"
    `ASR_BACKEND` IMMER explizit setzen — ohne Adapter-Auswahl fällt
    `get_client()` still auf pk-python zurück und postet gegen den
    ONNX-Container!

```bash
QWEN3_URL=http://qwen3-asr:8080 ASR_BACKEND=qwen3-asr \
  docker compose -f compose.yml -f compose.backends.yml --profile qwen3 up -d
```
