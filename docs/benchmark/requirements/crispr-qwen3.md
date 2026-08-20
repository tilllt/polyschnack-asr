# Backend: crispr-qwen3

CrispASR/qwen3-asr-server mit Qwen3-ASR-0.6B (q8_0) + Forced-Aligner-0.6B (f16).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr-qwen3:latest` (**privat**, image_login mit PAT) | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | erfolgreicher Lauf 19.08. |
| VRAM | 12 GB ausreichend | Lauf auf RTX 3060 (21:30, Norway) |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | **1,35 GB** (`qwen3-asr-0.6b-q8_0.gguf`) + **1,84 GB** (`qwen3-forced-aligner-0.6b-f16.gguf`) = **3,19 GB** (HF) | HEAD Content-Length 20.08. |
| Port / Health | 5094 / `/v1/audio/transcriptions` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set, 19.08.)

- WER **0,2795** · RTF 0,113 · Kosten ~0,0096 $ · Region Norway · Start gesamt ~284 s

## Besonderheiten

- Zwei GGUF-Downloads (ASR + Aligner) → längster Modell-Start der 12-GB-Gruppe.
- Server braucht `--convert` und Upload-Limit 1024 MB (Runner-onstart).
- Server-Start war historisch fehleranfällig (18.08.: 2× nicht bereit) — `slow_start`
  nicht gesetzt, aber Startzeit großzügig planen.
