# Modelle laden

Die GGUF-Modelle liegen in Bind-Mounts unter `./DATA/<name>-models/`
(keine Named-Volumes) und müssen **einmalig** geladen werden.

## parakeet.cpp (~700 MB)

```bash
docker run --rm -v "$PWD/DATA/cpp-models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```

## Qwen3-ASR (~3 GB, zwei Modelle)

```bash
docker run --rm -v "$PWD/DATA/qwen3-models:/models" alpine sh -c '
  wget -qO /models/qwen3-asr-0.6b-q8_0.gguf \
    https://huggingface.co/OpenVoiceOS/qwen3-asr-0.6b-q8-0/resolve/main/qwen3-asr-0.6b-q8_0.gguf &&
  wget -qO /models/qwen3-forced-aligner-0.6b-f16.gguf \
    https://huggingface.co/OpenVoiceOS/qwen3-forced-aligner-0.6b-f16/resolve/main/qwen3-forced-aligner-0.6b-f16.gguf
'
```

## ARK-ASR (~4 GB)

```bash
docker run --rm -v "$PWD/DATA/ark-models:/models" alpine wget -O /models/ark-asr-3b-q8_0.gguf \
  https://huggingface.co/cstr/ark-asr-3b-GGUF/resolve/main/ark-asr-3b-q8_0.gguf
```

## Moonshine-DE (~42 MB)

```bash
docker run --rm -v "$PWD/DATA/moonshine-models:/models" alpine sh -c '
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
docker run --rm -v "$PWD/DATA/canary-models:/models" alpine wget -O /models/canary-1b-v2-q4_k.gguf \
  https://huggingface.co/cstr/canary-1b-v2-GGUF/resolve/main/canary-1b-v2-q4_k.gguf
```

## Diarization-Modell (~470 MB)

```bash
docker run --rm -v "$PWD/DATA/diar-models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```

## Parakeet Python/ONNX

Das ONNX-Modell (~600 MB) wird beim ersten Start automatisch von HuggingFace
geladen — keine manuelle Aktion nötig.
