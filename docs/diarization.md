# Diarization (Sprechererkennung)

Die Diarization läuft **nicht in der Webapp** (kein pyannote, kein
CUDA-torch), sondern im eigenen `diar`-Container — einem schlanken
CrispASR-Server, der nur für die Sprechererkennung zuständig ist und
unabhängig vom gewählten ASR-Backend funktioniert:

- **Im Default-Stack enthalten** (`compose.yml` → `diar`), Healthcheck aktiv
- **GPU** via Overlay (`compose.gpu.yml` → `runtime: nvidia`), sonst CPU (ggml)
- Kein HF_TOKEN nötig — die Webapp ruft nur `POST /v1/audio/transcriptions`
  mit `diarize=true&response_format=diarized_json` auf

## Methoden

Die Methode ist per `DIARIZE_METHOD` wählbar (Webapp-Env):

| Methode | Beschreibung |
|---------|-------------|
| `pyannote` | Default. GGUF-Port des bekannten Modells. |
| `foxnose` | WeSpeaker-ResNet34 — laut CrispASR beste Accuracy, keine externen deps. |
| `energy` / `xcorr` / `vad-turns` | Leichtgewichtig. |

Die „Sprecheranzahl" aus der UI wird als `diarize_max_speakers` übertragen.

## Modell

Der Container lädt das Modell (parakeet-GGUF **q8_0**, ~640 MB) beim ersten
Start automatisch von HuggingFace in das Volume `./DATA/models/` —
das Volume muss dafür beschreibbar gemountet sein (in `compose.yml` bewusst
ohne `:ro`). Fehlt eine Datei, versucht der Entrypoint den Download bei jedem
Start erneut und gibt bei Fehlschlag eine Anleitung aus (siehe
`diar-service/entrypoint.sh`).

Manueller Download (z.B. wenn der Container keinen Internetzugang hat):

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```
