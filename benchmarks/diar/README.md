# Diarization-Benchmark (Change 136)

Misst die **Sprecher-Zuordnung** („wer spricht wann“) der im Stack
verfügbaren Diarisierungs-Methoden auf einem deutschen Testset mit exakter
Ground Truth.

## Testset: VoxPopuli-de-Mixe (CC0-1.0)

- **Quelle:** `facebook/voxpopuli` (de, Test-Split) — Europäisches Parlament,
  deutsch, **CC0-1.0 (Public Domain)** → frei als GitHub-Release
  veröffentlichbar.
- **Aufbau:** 20 Calls, 142 GT-Segmente, 2–4 Sprecher je Call, 32–102 s.
  Segmente verschiedener Sprecher werden deterministisch (Seed 42)
  aneinandergereiht (kurze Pausen) → **exakte GT** aus der Konstruktion.
- **Warum nicht CALLHOME German:** TalkBank/HF ist gated (403) +
  CC-BY-NC-SA (nicht-kommerziell) → ungeeignet für öffentliche Releases.
- **Builder:** `build_diar_testset.py --out assets/v1 --parquet <voxpopuli-de-test.parquet>`
  (Parquet-Download: `https://huggingface.co/datasets/facebook/voxpopuli/resolve/main/de/test-00000-of-00001.parquet`, ~936 MB)
- **Artefakte:** `assets/v1/diar-manifest.json` (Calls, Sprecher, GT),
  `assets/v1/audio/<call>.wav` (16 kHz mono), `SHA256SUMS`.

## Methoden unter Test (crispr-diar-Container)

| Methode | CLI/API | Anmerkung |
|---|---|---|
| foxnose | `--diarize-method foxnose` | WeSpeaker-Embedder + Clustering, mono-tauglich, **Default** |
| pyannote | `--diarize-method pyannote` | pyannote-seg-3.0-GGUF (nur Segmentierung; Embedder für stabile IDs) |
| vad-turns | `--diarize-method vad-turns` | pausenbasierte Turns, kein Modell (Baseline) |

Alle laufen über `POST /v1/audio/transcriptions` mit `response_format=diarized_json`
(siehe `webapp/app/diarize.py`; **wichtig:** `diarize_embedder=auto` erzwingen,
sonst bleiben Labels chunk-lokal — Change 126).

## Metriken (`diar_metrics.py`)

- **DER** (Diarization Error Rate): 1 − korrekt-zuordenbare Sprechzeit /
  GT-Sprechzeit, mit optimaler Sprecher-Zuordnung (brute force über
  Permutationen, ≤4 Sprecher/Call). Missed + False Alarm + Speaker Confusion
  sind darin enthalten. **Je kleiner desto besser.**
- **Jaccard je Segment:** mittlere beste segmentweise Jaccard-Ähnlichkeit.
- **Sprecherzahl-Fehler:** |n_GT − n_Hyp| je Call.
- **RTF:** Inferenzzeit / Audio-Dauer.

Selbsttest: `python3 diar_metrics.py` (asserts gegen bekannte Fälle).

## Ablauf (Selfservice)

```bash
# Im diar-Container / auf einem Host mit Zugriff auf diar + Webapp:
BENCHMARK_API_KEY=… \
DIAR_URL=http://localhost:5098 \
python3 diar_selfservice.py --submit https://whisper.cia-spandau.de \
    --method foxnose --backend crispr-diar-foxnose
```

1. `GET /api/benchmark/diarpackage/sha256` → Version + Paket-Hash
2. Paket lokal cachen / laden (`diar-manifest.json` + WAVs)
3. Je Call: Segmente via diar-Service → Metriken gegen GT
4. `POST /api/benchmark/submit` (kind="diar", HMAC-Signatur)

Einzelner Call: `python3 diar_run.py --audio call.wav --method foxnose --out segments.json`

## Webapp-Integration

- Paket-Quelle: lokal `DIAR_PACKAGE_LOCAL_DIR` (Default
  `benchmarks/diar/assets/v1`), Fallback `DIAR_PACKAGE_URL` (GitHub-Release
  `diar-set-v1`).
- Endpunkte: `/api/benchmark/diarpackage`, `/diarpackage/sha256`,
  `/diarsamples`, `/diaraudio/{id}`, `/diarpreview/{id}`.
- Ergebnisse: `latest.json["diar"]` → Diar-Tab (`DiarResultsTable`).
