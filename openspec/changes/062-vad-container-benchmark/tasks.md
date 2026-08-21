# Tasks — Change 062 (VAD-Container-Benchmark)

## Container

- [ ] `benchmarks/vad/containers/` Gerüst: gemeinsames `vad_run.py`-CLI
      (Audio → regions.json) + Dockerfile-Vorlage (schmal, Modell-Cache)
- [ ] Container je Modell: silero-onnx, ten-vad (sherpa), webrtc,
      humaware, speechbrain-crdnn, fsmn-vad, marble-net, cobra (AccessKey-Env)
- [ ] Lizenz-Matrix im Repo (produktiv nutzbar vs. Referenz)

## Selfservice + Submit

- [ ] `vad_selfservice.py`: Paket holen, Regionen messen, Metriken berechnen,
      POST submit (`kind: "vad"`)
- [ ] Webapp: `BenchmarkSubmit.kind` (asr|vad), VAD-Metriken in rows,
      VAD-Modell-Validierung (vad_models.yaml)
- [ ] Webapp: results/latest.json + Report VAD-Sektion
- [ ] Tests (Webapp: submit-kind-Tests; Selfservice-Smoke)

## vast

- [ ] `vad_benchmark_vast.py`: frische Instanz, Container starten, Lauf,
      Ergebnisse sichern, destroy (CPU-Klasse)
- [ ] Doku `docs/benchmark/index.md` VAD-Sektion + Lizenz-Matrix

## Abschluss

- [ ] Vollsuite, Commit, Push, CI
