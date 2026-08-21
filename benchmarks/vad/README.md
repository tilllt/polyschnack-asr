# VAD-Benchmark (Change 060/062)

Evidenzbasis für die VAD-Modellwahl in der Webapp — PolySchnack-Prinzip:
**nie raten, immer testen.** CPU-only, kein torch in der Webapp.

## Struktur

- `run_benchmark.py` — lokaler Benchmark (Testset + Metriken + Report)
- `vad_engines.py` — Engine-Registry (einheitliches Interface, Lizenz je Engine)
- `vad_run.py` — Container-CLI (Audio → regions.json)
- `vad_selfservice.py` — Remote-Selfservice (Paket holen → messen → submitten)
- `containers/` — Dockerfiles je VAD-Modell + Lizenz-Matrix
- `assets/` — Modelle/Testsets (gitignored, Download siehe unten)
- `/opt/data/scripts/vad_benchmark_vast.py` — vast.ai-Runner (frische Instanz je Test)

## Engines

| Engine | Modell | Lizenz | Integration |
|---|---|---|---|
| `silero_onnx` | silero_vad.onnx (2,3 MB, v6-stateful) | **MIT** | Webapp `app/vad.py` (onnxruntime) |
| `ten_vad` | ten-vad.onnx (sherpa-onnx-Port, 325 KB) | Apache-2.0 **+ Agora-Klauseln** | nur Benchmark — **nicht produktiv nutzbar** |
| `energy` | RMS-Schwelle (−40 dBFS) | — | deterministische Baseline |

**Lizenz-Fund (2026-08-21):** TEN VAD ist Apache-2.0 mit Zusatzbedingungen
([LICENSE](https://github.com/TEN-framework/ten-vad/blob/main/LICENSE)) —
Punkt 1 verbietet Deploy, das mit Agoras Angeboten konkurriert. Ein
selbst-gehosteter ASR-Dienst (PolySchnack) kollidiert damit → **TEN VAD
scheidet für die Produktintegration aus**, trotz Benchmark-Leistung.

## Testset

- **A) DE-Synthese** (`benchmark/data/tts`, Piper-de-DE): deterministische
  Stille-Insertion (2 s vorne / hinten / beide / 1-s-Lücke mittig) →
  exakte Ground Truth (Energie-GT der Quelle + Insertions-Offset, VAD-frei).
- **B) TEN-Testset** (assets/tenvad/testset-audio-*.scv): offizielle,
  frame-annotierte GT (Vendor-Set, Referenz).
- **C) Noise-FP**: weißes Rauschen (DEMAND-Teilmenge folgt) — jede erkannte
  Speech-Zeit in reinem Rauschen ist ein False Positive.

## Metriken

- **Boundary-Fehler (ms)**: |pred_start − gt_start|, |pred_end − gt_end|
  für IoU-gematchte Regionen — kritisch für den Trim-Offset.
- **Region-F1**: Overlap-Matching (IoU > 0,5).
- **FP-Speech-Zeit (s)** auf Noise-Samples.
- **RTF**: Inferenzzeit / Audiodauer (Session-Init ausgenommen).

## Lauf

```bash
uv venv .venv && uv pip install --python .venv/bin/python sherpa-onnx onnxruntime numpy httpx
.venv/bin/python run_benchmark.py --max-tts 12
```

Ergebnisse: `out/results.md` + `out/results.json` → Entscheidung mit Quellen
in `docs/component-decisions.md` (Change 060).

## Quellen

- [silero-vad (MIT)](https://github.com/snakers4/silero-vad)
- [TEN VAD (Agora)](https://github.com/TEN-framework/ten-vad) + [sherpa-Port](https://k2-fsa.github.io/sherpa/onnx/vad/ten-vad.html)
- [Picovoice voice-activity-benchmark (Methodik: FPR/TPR-ROC)](https://github.com/Picovoice/voice-activity-benchmark)
- DEMAND-Noise: [HF-Mirror (CC-BY-4.0)](https://huggingface.co/datasets/voice-biomarkers/DEMAND-acoustic-noise)
