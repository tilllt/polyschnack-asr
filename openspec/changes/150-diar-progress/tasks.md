# Change 150 — Tasks (Diarization-Progress)

## 1. CrispASR-Server (Fork, upstream-PR)

- [x] `examples/cli/crispasr_server.cpp`: `g_server_progress`/`g_server_busy`
      (atomic) + `progress_scope`-Guard in `do_transcribe`
- [x] Fortschritt in der Chunk-Schleife (`i+1`/`slices.size()` → 0..100)
- [x] `GET /progress` → `{"busy": bool, "progress": -1..100}`
- [ ] Lokaler Build + Smoke-Test (Server starten, /progress pollt 0→100)
- [ ] PR gegen CrispStrobe/CrispASR (eigener Branch von origin/main,
      NUR die /progress-Commits — nicht der diarize-Branch)

## 2. Webapp (dieses Repo)

- [x] `diarize.py`: `on_progress`-Callback + Poller-Thread (Daemon,
      stop-Event im finally; eigener kurzer httpx-Client)
- [x] `service.py`: `_run_diarization(on_progress)`; `_report_diar_progress`
      (eigene Session, note="diarization X%", Phase 96)
- [x] Aufruf in `_run_background_rediarize`: Lambda + Phase-Set vor dem POST
- [x] Frontend: `activePhaseIndex` matcht "diarization X%";
      `phaseDetail` zeigt "X%" (analog "Chunk X/Y")
- [x] Tests: `test_diarize_progress.py` (2 Tests, MockTransport)
- [ ] Vollständige Backend-Suite + Commit + Push

## 3. Verifikation

- [ ] Nach Deploy: Diarization zeigt echte Server-Prozente
- [ ] crispr-sep (htdemucs): separater Folge-Change (kein /progress im
      htdemucs-Pfad)
