# Architektur

```mermaid
graph LR
    Browser -->|HTTP :8088| webapp["webapp<br/>(FastAPI + SQLite)"]
    webapp -->|OpenAI-API| asr["asr (Python/ONNX)<br/>oder pk-cpp<br/>oder qwen3-asr<br/>oder ark-asr …"]
    webapp -->|Diarization| diar["diar (CrispASR-Server)"]
    webapp -->|Docker-API| proxy["docker-proxy<br/>(Socket-Proxy)"]
    proxy -.start/stop.-> asr
    asr --> model["ASR Modell (GGUF / ONNX)"]
    webapp --- db[("SQLite + Audio-Dateien<br/>(./DATA/poc-data)")]
    asr --- mcache[("Modell-Cache<br/>(./DATA/<name>-models)")]
```

Die Webapp kommuniziert mit den ASR-Backends über die OpenAI-kompatible
`POST /v1/audio/transcriptions`-Schnittstelle. Der Adapter wird durch die
Umgebungsvariable `ASR_BACKEND` gesteuert (jedes Backend hat seine eigene
URL-Env — siehe [Backend-Übersicht](backends/overview.md)).

Die Diarization läuft im eigenen `diar`-Container (CrispASR-Server,
`POST /v1/audio/transcriptions` mit `diarize=true&response_format=diarized_json`).

Die Admin-GUI steuert die Backend-Container über den restriktiven
`docker-proxy` (kein direkter Docker-Socket-Zugriff aus der Webapp).

## Wichtige Design-Entscheidungen

- **Webapp ist CPU-only** — kein torch/pyannote im Image, ~2,5–3 GB schlanker.
- **Diarization als eigener Container** — unabhängig vom ASR-Backend wählbar.
- **Hybride Backend-Images** — CUDA-Binary mit CPU-Fallback, GPU nur via
  Overlay (siehe [Quickstart](quickstart.md)).
