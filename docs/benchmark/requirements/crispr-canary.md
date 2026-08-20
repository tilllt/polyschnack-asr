# Backend: crispr-canary

CrispASR (C++) mit NVIDIA Canary-1B-V2 (GGUF q4_k).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr-canary:latest` (public seit 18.08.) | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | erfolgreiche Läufe 18./19.08. |
| VRAM | 12 GB ausreichend | Läufe auf RTX 3060 |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | **0,61 GB** (`canary-1b-v2-q4_k.gguf`, HF) | HEAD Content-Length 20.08. |
| Port / Health | 5097 / `/health` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set, 19.08.)

- WER **0,2703** · RTF 0,078 · Kosten ~0,0024 $ · Region Finland · Start gesamt ~83 s

## Besonderheiten

- 1B-Architektur, q4_k → kompaktes Modell, schneller Start.
- WER auf dem 207er-Set hinter Parakeet (0,16x), vor Moonshine/Whisper-Schnelltest.
