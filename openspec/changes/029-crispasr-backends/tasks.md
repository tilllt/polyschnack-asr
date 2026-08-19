# Change 029 — Tasks

## Images
- [ ] `voxtral-crisp/Dockerfile` (CrispASR v0.8.29, `--backend voxtral4b`,
      Port 5100, Hybrid CUDA/CPU) — Vorlage ark-asr-cpp
- [ ] `whisper-crisp/Dockerfile` (CrispASR v0.8.29, `--backend whisper`,
      Port 5101, Hybrid CUDA/CPU)

## CI
- [ ] `.gitlab-ci.yml`: Jobs `build-voxtral` + `build-whisper-crisp`
- [ ] `mirror-github` needs ergänzen; `mirror-ghcr`-Liste erweitern

## Einbindung
- [ ] `compose.backends.yml`: Profile `crispr-voxtral` (5100) + `crispr-whisper` (5101)
- [ ] `webapp/app/backends.yaml`: Blöcke crispr-voxtral + crispr-whisper
      (Adapter CrispAsrHttpClient, model_files-URLs)

## Verifikation
- [ ] YAML-Validierung lokal (pyyaml)
- [ ] Commit + Push; CI grün (Build-Jobs + Mirror); Harbor-Tags prüfen
- [ ] Smoke-Test (optional): CrispASR-Binary auf Instanz — voxtral4b + whisper
      transkribieren je 1 deutsches Sample
