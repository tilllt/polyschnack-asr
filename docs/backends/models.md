# Modelle laden

Alle GGUF-Modelle liegen in einem **gemeinsamen Bind-Mount** unter
`./DATA/models/` (keine Named-Volumes) — alle Backends und der diar-Service
mounten denselben Ordner auf `/models`. Der Container-Name pro Service wird
nur über die Env-Variablen (`CPP_ASR_MODEL`, `DIAR_MODEL`, …) gesteuert.

Der **diar-Service lädt sein Modell automatisch** beim ersten Start
(siehe `diar-service/entrypoint.sh`). Für die Backends muss geladen werden:

## parakeet.cpp (~640 MB)

**Dasselbe Modell nutzt auch der diar-Service — nur einmal laden!**

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```

## Qwen3-ASR (~3 GB, zwei Modelle)

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine sh -c '
  wget -qO /models/qwen3-asr-0.6b-q8_0.gguf \
    https://huggingface.co/OpenVoiceOS/qwen3-asr-0.6b-q8-0/resolve/main/qwen3-asr-0.6b-q8_0.gguf &&
  wget -qO /models/qwen3-forced-aligner-0.6b-f16.gguf \
    https://huggingface.co/OpenVoiceOS/qwen3-forced-aligner-0.6b-f16/resolve/main/qwen3-forced-aligner-0.6b-f16.gguf
'
```

## ARK-ASR (~4 GB)

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/ark-asr-3b-q8_0.gguf \
  https://huggingface.co/cstr/ark-asr-3b-GGUF/resolve/main/ark-asr-3b-q8_0.gguf
```

## Moonshine-DE (~42 MB)

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine sh -c '
  wget -qO /models/moonshine-base-de-fidoriel-q4_k.gguf \
    https://huggingface.co/cstr/moonshine-base-de-fidoriel-GGUF/resolve/main/moonshine-base-de-fidoriel-q4_k.gguf &&
  wget -qO /models/tokenizer.bin \
    https://huggingface.co/cstr/moonshine-base-de-fidoriel-GGUF/resolve/main/tokenizer.bin
'
```

!!! warning "Lizenz"
    Moonshine-DE: **CC-BY-NC-SA-4.0** — nicht für kommerzielle Nutzung.

## Canary (~0,6 GB)

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/canary-1b-v2-q4_k.gguf \
  https://huggingface.co/cstr/canary-1b-v2-GGUF/resolve/main/canary-1b-v2-q4_k.gguf
```

## Diarization-Modell (~640 MB)

Der diar-Service lädt das Modell beim ersten Start **automatisch** von
HuggingFace in `./DATA/models/` (Volume beschreibbar gemountet). Nur wenn der
Container keinen Internetzugang hat, manuell (gleiche Datei wie parakeet.cpp):

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```

## Parakeet Python/ONNX

Das ONNX-Modell (~600 MB) wird beim ersten Start automatisch von HuggingFace
geladen — keine manuelle Aktion nötig.
