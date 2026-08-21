# Change 062 — VAD-Modell-Container-Benchmark (vast remote + Submit)

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

Der VAD-Benchmark (Change 060) läuft nur lokal (einige Engines, CPU).
Der User will:
1. **Custom-Docker-Container für VAD-Modelle** — auch Modelle mit
   lizenz-inkompatiblen Bedingungen (Cobra, TEN VAD, MarbleNet …) als
   Referenz benchmarkbar, bewusst getrennt von der Produktnutzung.
2. **Tests auf vast.ai** (wie der ASR-Benchmark: frische Instanz je Test).
3. **Reporting-Erweiterung**: VAD-Container können remote gebenchmarkt
   werden und ihre Ergebnisse an die Webapp submitten (Selfservice-Muster
   Change 030/031).

## Ziel

Einheitliche VAD-Container + Selfservice-Submit + vast-Skript, sodass jedes
VAD-Modell gegen dasselbe Testset (DE-Synthese mit exakter GT, DEMAND-Noise,
MUSAN/Babble bei SNR-Stufen) gemessen und zentral im Benchmark-Reporting
(whisper.cia-spandau.de) gesammelt wird.

## Umsetzung (Skizze)

1. **VAD-Container** (`benchmarks/vad/containers/<model>/`):
   - Einheitliches CLI: `vad_run.py --audio in.wav --out regions.json`
     → `{"regions": [{"start": s, "end": e}, …], "rtf": r}`
   - Modelle: `silero-onnx` (MIT), `ten-vad` (Agora-Klausel),
     `cobra` (kommerziell, AccessKey via Env), `marble-net` (NVIDIA),
     `speechbrain-crdnn`, `humaware` (MIT), `webrtc` (BSD),
     `fsmn-vad` (Apache-2.0). Jede Lizenz im Container-README dokumentiert;
     PolySchnack-produktiv nutzbar nur die kompatiblen.
2. **`vad_selfservice.py`** (analog `benchmark_selfservice.py`, Change 030):
   - GET `/api/benchmark/package` (+sha256) → Paket
   - je Sample VAD-Regionen berechnen → Metriken (Boundary-Fehler ms,
     Region-F1, FP-Zeit, RTF) gegen GT im Manifest
   - POST `/api/benchmark/submit` mit `kind: "vad"`
3. **Webapp-Erweiterung** (`app/routers/benchmark.py` + Service):
   - `BenchmarkSubmit.kind: Literal["asr","vad"]` (Default "asr"),
     VAD-Metriken in `rows` (kein WER-Pflichtfeld), VAD-Modelle in der
     Backend-Validierung erlauben (eigene `vad_models.yaml` o. `backends.yaml`-Typ)
   - `results/latest.json` + Report zeigen VAD-Sektion (Modell-Tabelle)
4. **`vad_benchmark_vast.py`** (`/opt/data/scripts/`):
   - `start_timing_vast`-Module wiederverwenden (search_offers/rent/
     wait_ready/destroy); je Test frische Instanz; VAD ist CPU-light →
     günstige Klasse; nach Ready echter Lauf, Ergebnisse sichern
     (`/opt/data/vast-benchmarks/logs/`), Instanz destroy.
5. **Doku**: `docs/benchmark/index.md` (VAD-Sektion), Lizenz-Matrix
   (`Lizenz`, `produktiv nutzbar?`) — kompatibel vs. Referenz.

## Referenzen

- Selfservice-Muster: `polyschnack-benchmark/benchmark/scripts/benchmark_selfservice.py`
  (Change 030/031, Shared-Key + HMAC-Signatur)
- Submit-Schema: `webapp/app/routers/benchmark.py` (`BenchmarkSubmit`)
- vast-Module: `/opt/data/scripts/start_timing_vast.py`
  (`backend_benchmark_full.py`-Muster)
- VAD-Modell-Lizenzen: siehe Change-060-Doku (`docs/component-decisions.md`)
