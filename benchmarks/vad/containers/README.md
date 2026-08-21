# VAD-Benchmark-Container (Change 062)

Jeder Container bündelt **eine** VAD-Engine aus `vad_engines.py` + das
einheitliche CLI `vad_run.py` + den Selfservice `vad_selfservice.py`.

## Lizenz-Matrix

| Container | Engine | Lizenz | Produktiv in PolySchnack |
|---|---|---|---|
| `vad-silero-onnx` | silero_onnx | MIT | ✅ |
| `vad-webrtc` | webrtc | BSD-3-Clause | ✅ (Baseline) |
| `vad-humaware` | humaware | MIT (Forschung) | ✅* |
| `vad-speechbrain` | speechbrain | Apache-2.0 (EN-trainiert) | ✅* |
| `vad-ten-vad` | ten_vad | Apache-2.0 + **Agora-Klauseln** | ❌ NUR Referenz |
| `vad-cobra` | cobra | **kommerziell (Picovoice, AccessKey)** | ❌ NUR Referenz |
| `vad-marble-net` | marble_net | **NVIDIA "other"** | ❌ NUR Referenz |
| `vad-fsmn-vad` | fsmn_vad | Apache-2.0 | ✅ |

*Qualitativ zu prüfen (Forschung / EN-only) — Silero-onnx bleibt Default.

## Build + Lauf

```bash
# silero-onnx (Build-Kontext = benchmarks/vad/)
docker build -f containers/Dockerfile.silero-onnx -t ghcr.io/tilllt/polyschnack-vad-silero:latest .

# Lokal (ein Sample):
docker run --rm -v $PWD/out:/out ghcr.io/tilllt/polyschnack-vad-silero:latest \
    python vad_run.py --audio /out/audio/de_00_lead2.wav --out /out/regions.json

# Selfservice (Paket vom Server holen + Ergebnisse submitten):
docker run --rm \
    -e BENCHMARK_API_KEY=... -e VAD_BACKEND=silero-onnx -e VAD_ENGINE=silero_onnx \
    ghcr.io/tilllt/polyschnack-vad-silero:latest
```

## Remote (vast.ai)

`/opt/data/scripts/vad_benchmark_vast.py` mietet je Test eine frische
Instanz (CPU-Klasse reicht — VAD ist leichtgewichtig), startet den
Container, sammelt die Ergebnisse (vad_results.json) und zerstört die
Instanz. Ergebnisse landen zusätzlich als Submit auf der Webapp
(whisper.cia-spandau.de, `/api/benchmark/vadpackage` + `/submit` kind=vad).
