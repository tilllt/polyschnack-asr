# VAD-Benchmark (Change 060/062/064)

Evidenzbasis für die VAD-Modellwahl in der Webapp — PolySchnack-Prinzip:
**nie raten, immer testen.** CPU-only, kein torch in der Webapp.

## Struktur

- `run_benchmark.py` — lokaler Benchmark (Testset + Metriken + Report)
- `build_testset_v3.py` — V3.1-Testset-Builder (TTS + Common-Voice, public/heldout)
- `assemble_release_zip.py` — Release-ZIP (public + PROVENANCE.md + SHA256SUMS)
- `vad_engines.py` — Engine-Registry (einheitliches Interface, Lizenz je Engine)
- `vad_run.py` — Container-CLI (Audio → regions.json)
- `vad_selfservice.py` — Remote-Selfservice (Paket holen → messen → submitten)
- `containers/` — Dockerfiles je VAD-Modell + Lizenz-Matrix
- `assets/` — Modelle/Testsets (gitignored, Download siehe unten)
- `/opt/data/scripts/vad_benchmark_vast.py` — vast.ai-Runner (frische Instanz je Test)

## V4-Testset (offizielle Storage, Change 063/064/081)

Das Testset liegt als Release-Artefakt auf GitHub:
[tilllt/vad-benchmark-data](https://github.com/tilllt/vad-benchmark-data).

- **Release v3** (historisch): `vad-testset-v3.tar.gz`, 101 TTS-Samples.
- **Release v4** (historisch): `vad-benchmark-v3.1-public.zip` — 235 public
  Samples, TTS noch Thorsten/Ramona.
- **Release v5** (aktuell): `vad-benchmark-v4-public.zip` — **235 public
  Samples** (Piper-TTS Thorsten/VibeVoice + Common-Voice-DE, DEMAND-SNR
  0/5/10 dB, Babble, TEN, Noise, MUSAN-Musik) + `testset.json` +
  `PROVENANCE.md` + `SHA256SUMS`. Für externe User: ZIP mit
  Quellen/Lizenzen/Seeds, nicht einzeln.

```bash
# Manuell (run_benchmark.py --v3 lädt automatisch, wenn lokal fehlt):
curl -L -o assets/v3/vad-testset-v4-public.zip \
  https://github.com/tilllt/vad-benchmark-data/releases/download/v5/vad-benchmark-v4-public.zip
```

### public/held-out-Split (Change 064)

- **public** (235 Samples) → GitHub-Release/ZIP/Repo/Container-Images.
- **heldout** (126 Samples, `assets/v3-heldout/`) → **NUR lokal**, gitignored.
  Warum: Sobald ein Testset öffentlich ist, kann es in Trainingsdaten
  einfließen (Leakage) → die Benchmark-Zahlen wären nicht mehr ehrlich.
  `run_benchmark.py --split heldout` lädt heldout **nie** vom Release und
  bricht ohne lokales Verzeichnis ab. Das Repo/Mirror (GitHub, Harbor)
  enthält niemals held-out-Audio.

Determinismus: feste Seeds + sortierte Iteration + gzip-mtime=0 →
identische Artefakte bei Wiederholung; SHA256 je Artefakt im GitHub-Release.
Neuer Stand: `build_testset_v3.py --split all` generiert public+heldout,
dann Release v(N+1) erstellen (nur public!).

## Engines

| Engine | Modell | Lizenz | Integration |
|---|---|---|---|
| `silero_onnx` | silero_vad.onnx (2,3 MB, v6-stateful) | **MIT** | Webapp `app/vad.py` (onnxruntime) |
| `ten_vad` | ten-vad.onnx (sherpa-onnx-Port, 325 KB) | Apache-2.0 **+ Agora-Klauseln** | nur Benchmark — **nicht produktiv nutzbar** |
| `webrtc` | webrtcvad (BSD) | BSD | Referenz-Baseline |
| `humaware` | HumAware-VAD (MIT, torch) | **MIT** | Benchmark (Forschung) |
| `speechbrain` | CRDNN (EN-only) | Apache-2.0 | Benchmark (nur EN) |
| `fsmn_vad` | FunASR FSMN-VAD (Apache-2.0, multilingual) | Apache-2.0 | Benchmark |
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
- **A2) Common Voice DE** (`benchmark/data/common_voice`, CC0, 24 WAVs
  akzent/child/clean, Seed-42-Auswahl): echte Sprache mit Mikrofon-/Raum-
  rauschen — realistischste VAD-Bedingung; pur (Stille-Insertion) und
  DEMAND-SNR 0/5/10 dB (GT bleibt exakt, da Speech-Regionen deterministisch).
- **B) TEN-Testset** (assets/tenvad/testset-audio-*.scv): offizielle,
  frame-annotierte GT (Vendor-Set, Referenz).
- **C) Noise-FP**: weißes Rauschen + DEMAND — jede erkannte Speech-Zeit in
  reinem Rauschen ist ein False Positive.
- **D) Musik-FP**: MUSAN-Music (CC-BY-4.0) — Musik ist keine Sprache.

## Metriken

- **Boundary-Fehler (ms)**: |pred_start − gt_start|, |pred_end − gt_end|
  für IoU-gematchte Regionen — kritisch für den Trim-Offset.
- **Region-F1**: Overlap-Matching (IoU > 0,5).
- **FP-Speech-Zeit (s)** auf Noise-Samples.
- **RTF**: Inferenzzeit / Audiodauer (Session-Init ausgenommen).

## Lauf

```bash
uv venv .venv && uv pip install --python .venv/bin/python sherpa-onnx onnxruntime numpy httpx
.venv/bin/python run_benchmark.py --max-tts 12          # Legacy-Testset
.venv/bin/python run_benchmark.py --v3 --split all      # V3.1 public + heldout
.venv/bin/python run_benchmark.py --v3 --split public   # nur public
.venv/bin/python run_benchmark.py --v3 --split heldout  # nur lokal, nie vom Release
```

Ergebnisse: `out/results_v3_public.md/json` + `out/results_v3_heldout.md/json`
→ Entscheidung mit Quellen in `docs/component-decisions.md` (Change 060/064).

## Quellen

- [silero-vad (MIT)](https://github.com/snakers4/silero-vad)
- [TEN VAD (Agora)](https://github.com/TEN-framework/ten-vad) + [sherpa-Port](https://k2-fsa.github.io/sherpa/onnx/vad/ten-vad.html)
- [Picovoice voice-activity-benchmark (Methodik: FPR/TPR-ROC)](https://github.com/Picovoice/voice-activity-benchmark)
- [FSMN-VAD (FunASR, Apache-2.0)](https://huggingface.co/funasr/fsmn-vad)
- DEMAND-Noise: [HF-Mirror (CC-BY-4.0)](https://huggingface.co/datasets/voice-biomarkers/DEMAND-acoustic-noise)
- Common Voice DE: [Mozilla Common Voice](https://commonvoice.mozilla.org/de) (CC0-1.0)
