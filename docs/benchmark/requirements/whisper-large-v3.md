# Backend: whisper-large-v3

OpenAI-Whisper large-v3 via faster-whisper (OpenAI-kompatibler Server, Python).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `harbor.rand0m.me/public/polyschnack-asr-whisper:latest` | Runner-Backend-Tabelle |
| Image-Größe | **2,51 GB** | Harbor-API 20.08. |
| GPU-Klasse | RTX 3060 / RTX 4070 (12 GB) | Instanz 48171249 (3060, 19.08.) |
| VRAM | 12 GB ausreichend | faster-whisper large-v3 (ct2) auf 3060 |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell | faster-whisper `large-v3` (**model.bin ~3 GB, im Image**) | Repo Systran/faster-whisper-large-v3; Image-Env `ASR_MODEL=large-v3` |
| Port / Health | 8000 / `/health` | Runner-Tabelle |
| slow_start | **Ja** — Modell lädt beim Container-Start (mehrere GB) | Runner-Flag |
| RAM (Host, beobachtet) | 128–257 GB | vast-Mietangebote 3060 |

## Benchmark (207er-Set)

- Lauf 20.08. (Nachlauf, Change 033) — Ergebnis folgt in `result_benchmark_whisper-large-v3.json`.
- Schnelltest 19.08. (3090-Reuse): WER 0,2788 · RTF 0,030.

## Besonderheiten

- **Registry:** Harbor statt GHCR — GHCR-anonymer Pull von vast hängt (Rate-Limit
  geteilte IPs, 2× belegt 19.08.); Harbor ohne Limit.
- Modell-Pull + Server-Start übernimmt das Image (onstart nur `echo onstart-ok`).
- Sprach-Override je Request (de/en je Kategorie) im Benchmark-Runner.
