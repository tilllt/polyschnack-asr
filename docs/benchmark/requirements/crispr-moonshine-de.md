# Backend: crispr-moonshine-de

CrispASR (C++) mit Moonshine-Base-DE (fidoriel, q4_k) — deutsches ASR-Modell.

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr-moonshine-de:latest` | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | erfolgreiche Läufe 18./19.08. |
| VRAM | 12 GB ausreichend | Läufe auf RTX 3060 |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | **0,04 GB** (`moonshine-base-de-fidoriel-q4_k.gguf`) + `tokenizer.bin` (HF) — kleinstes Modell der Gruppe | HEAD Content-Length 20.08. |
| Port / Health | 5096 / `/health` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set, 19.08.)

- WER **0,2683** · RTF 0,060 · Kosten ~0,0018 $ · Region Finland · Start gesamt ~63 s

## Besonderheiten

- Lizenz: **CC-BY-NC-SA-4.0** (via `CRISPASR_ACCEPT_LICENSE` im onstart) —
  nur für nicht-kommerzielle Nutzung.
- Winziges Modell → schnellster Modell-Start der Gruppe (63 s gesamt).
- RTF günstig (0,06), WER hinter Parakeet/Canary.
