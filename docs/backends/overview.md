# Backend-Übersicht

PolySchnack unterstützt **mehrere ASR-Engines**. Du wechselst einfach per
Env-Variable — kein Code nötig.

| Backend | Profil | CLI-Name | Beschreibung |
|---------|--------|----------|-------------|
| **Parakeet (Python/ONNX)** | *(Default)* | `ps-pk-onnx` | Das Original-Modell von NVIDIA, 0,6B Parameter. Hybrid: GPU (CUDA) oder CPU (INT8), auto-detect. |
| **parakeet.cpp (ggml/C++)** | `--profile crispr-pk-cpp` | `crispr-pk-cpp` | Gleiches Modell, aber in C++ — schneller und schlanker (~700 MB quantisiert). Native Interpunktion + deutsches Truecasing. |
| **Qwen3-ASR (ggml/C++)** | `--profile crispr-qwen3` | `crispr-qwen3` | Neuestes ASR-Modell von Alibaba, 30 Sprachen, **Word-Timestamps** via ForcedAligner (~3 GB beide Modelle). |
| **ARK-ASR (ggml/C++)** | `--profile crispr-ark` | `crispr-ark` | State-of-the-Art auf dem HF ASR Leaderboard, 3B Parameter, Whisper-Encoder + Qwen2.5-Decoder. |
| **Moonshine-DE (ggml/C++)** | `--profile crispr-moonshine-de` | `crispr-moonshine-de` | Kompaktes deutsches Spezialmodell (61,5M Parameter, 6,9 % WER auf CV22-de, ~39 MB GGUF). ⚠️ Lizenz CC-BY-NC-SA-4.0 (nicht-kommerziell). |
| **Canary (ggml/C++)** | `--profile crispr-canary` | `crispr-canary` | NVIDIA Canary 1B v2 — multilingual (EN/DE/FR/ES). |

## Adapter-URLs

Jeder Adapter hat **seine eigene URL-Env** — nie `ASR_URL` für andere
Backends verwenden (das ist der ONNX-ps-pk-onnx-Container!):

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASR_BACKEND` | `ps-pk-onnx` | Adapter-Auswahl (`ps-pk-onnx`, `crispr-pk-cpp`, `crispr-qwen3`, `crispr-ark`, `crispr-moonshine-de`, `crispr-canary`) |
| `ASR_URL` | `http://ps-pk-onnx:5092` | URL des ONNX-ps-pk-onnx-Containers |
| `CRISPR_PK_CPP_URL` | `http://crispr-pk-cpp:5093` | URL des pk-cpp-Containers (CrispASR parakeet) |
| `CRISPR_QWEN3_URL` | `http://crispr-qwen3:5094` | URL des Qwen3-ASR-Containers |
| `CRISPR_ARK_URL` | `http://crispr-ark:5095` | URL des ARK-ASR-Containers (CrispASR) |
| `CRISPR_MOONSHINE_DE_URL` | `http://crispr-moonshine-de:5096` | URL des Moonshine-DE-Containers |
| `CRISPR_CANARY_URL` | `http://crispr-canary:5097` | URL des Canary-Containers |

!!! warning "Adapter-Auswahl nie vergessen"
    `ASR_BACKEND` IMMER explizit setzen — ohne Adapter-Auswahl fällt
    `get_client()` still auf pk-python zurück und postet gegen den
    ONNX-Container!

```bash
CRISPR_QWEN3_URL=http://crispr-qwen3:5094 ASR_BACKEND=crispr-qwen3 \
  docker compose -f compose.yml -f compose.backends.yml --profile crispr-qwen3 up -d
```
