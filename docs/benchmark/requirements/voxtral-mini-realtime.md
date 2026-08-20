# Backend: voxtral-mini-realtime

Mistral Voxtral-Mini-4B-Realtime-2602, serviert mit vLLM (OpenAI-kompatibel).

| Ressource | Wert | Beleg |
|---|---|---|
| Image | `vllm/vllm-openai:latest` | Runner-Backend-Tabelle |
| Image-Größe | **10,53 GB** | Docker-Hub-API 20.08. |
| GPU-Klasse | **RTX 3090 / RTX 4090 (24 GB)** — NICHT 3060/4070 | VAST_GPU_PREF-Override (Change 033); Schnelltest auf 3090 (19.08.) |
| VRAM | **16 GB+ laut Modellkarte** (24 GB empfohlen) | Kommentar im Runner (belegt 19.08.); 12-GB-Karten reichen NICHT |
| Miet-Disk | ≥ 30 GB | Runner `DISK_GB=30` |
| Modell | `mistralai/Voxtral-Mini-4B-Realtime-2602` — vLLM lädt es bei Start von HF (~4B-Parameter) | Runner-onstart |
| Port / Health | 8000 / `/health` | Runner-Tabelle |
| slow_start | **Ja** — vLLM lädt 10+ GB, Port bleibt lange zu | Runner-Flag |
| RAM (Host, beobachtet) | 128–257 GB (3060-Angebote); 24-GB-Hosts i. d. R. mehr | vast-Angebote |

## Benchmark (207er-Set)

- Lauf 20.08. (Nachlauf, Change 033, VAST_GPU_PREF="RTX 3090, RTX 4090") —
  Ergebnis folgt in `result_benchmark_voxtral-mini-realtime.json`.
- Schnelltest 19.08. (3090-Reuse): WER 0,2321 · RTF 0,114.

## Besonderheiten

- **vLLM-Pflichtoptionen:** `--compilation-config '{"cudagraph_mode":"PIECEWISE"}'`
  (AssertionError sonst, belegt 19.08.), `--tokenizer-mode mistral`,
  `--load-format mistral`, `--max-model-len 16000`, `--max-num-seqs 1`,
  `--gpu-memory-utilization 0.92`, served-model-name `whisper-1`.
- `pip install 'mistral-common[soundfile]'` vorab (ImportError belegt 19.08.).
- Lizenz: **Apache-2.0** (Modellkarte, belegt 19.08.).
- GPU-Auswahl im Runner: `VAST_GPU_PREF="RTX 3090, RTX 4090"` (Default bleibt
  3060/4070) — sonst mietet der Runner zu kleine Karten und der Lauf hängt.
