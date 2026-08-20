# Backend: crispr-ark

CrispASR (C++) mit NVIDIA Ark-ASR-3B (GGUF q8_0).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `ghcr.io/tilllt/polyschnack-asr-ark:latest` | Runner-Backend-Tabelle |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | Annahme (läuft in der 12-GB-Klasse, kein Erfolgslauf) |
| VRAM | 12 GB erwartet ausreichend (3B-q8 ≈ 4,3 GB Modell) | Modellgröße belegt, Lauf offen |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell-Download | **4,29 GB** (`ark-asr-3b-q8_0.gguf`, HF) — größter GGUF der Gruppe | HEAD Content-Length 20.08. |
| Port / Health | 5095 / `/health` | Runner-Tabelle |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set)

- **Kein Ergebnis:** 18.08. UTF-8-Fehler + WER ~1,0 bei ~80 %, englische
  Halluzinationen; 19.08. ark erneut fehlgeschlagen. Backend gilt als
  **blockiert** bis Fehleranalyse (siehe component-decisions).

## Besonderheiten

- `--no-punctuation` im onstart (kein Punc-Modell).
- Größter Modell-Download → längster Modell-Start erwartet.
