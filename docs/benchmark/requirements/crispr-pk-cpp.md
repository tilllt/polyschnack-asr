# Backend: crispr-pk-cpp

CrispASR (C++) mit NVIDIA Parakeet-TDT-0.6B-V3 (GGUF q8_0).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr-cpp:latest` | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | erfolgreiche Läufe 18./19.08. |
| VRAM | 12 GB ausreichend | Läufe auf RTX 3060 |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | **0,67 GB** (`parakeet-tdt-0.6b-v3-q8_0.gguf`, HF) | HEAD Content-Length 20.08. |
| Port / Health | 5093 / `/health` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set, 19.08.)

- WER **0,1619** · RTF 0,092 · Kosten ~0,022 $ · Region Norway · Start gesamt ~224 s

## Besonderheiten

- GGUF-Download bei jedem Instanz-Start (0,67 GB, ~1–2 min je nach Anbindung).
- Schnellster RTF der CrispASR-Gruppe in Kombination mit Parakeet.
