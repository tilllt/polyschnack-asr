# Backend: ps-pk-onnx

PolySchnack-Server (Python/ONNX) — Parakeet-TDT-0.6B.

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr:latest` | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | erfolgreiche Läufe 18./19.08. |
| VRAM | 12 GB ausreichend | Läufe auf RTX 3060 |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | keiner (Modell im Image, ONNX) | onstart: nur `server.py`-Start |
| Port / Health | 5092 / `/health` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set, 19.08.)

- WER **0,1615** · RTF 0,075 · Kosten ~0,0024 $ · Region Finland · Start gesamt ~89 s

## Besonderheiten

- Referenz-Implementierung der PolySchnack-ASR (Python-Pipeline im Image).
- Start ohne externe Downloads → schnellstes Provisioning der Gruppe.
