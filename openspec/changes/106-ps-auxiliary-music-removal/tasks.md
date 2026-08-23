# Tasks — Change 106 (ps-auxiliary: Rename + Music Removal)

## Phase 0 — Doku-Rename ps-post → ps-auxiliary
- [ ] `openspec/changes/020-remote-inference-workers/proposal.md`: ps-post → ps-auxiliary
- [ ] `openspec/changes/022-ps-post-punctuation/` (proposal/design/tasks/2 specs): ps-post → ps-auxiliary; Hinweis ergänzen, dass Supervisor-Container bewusst nicht gebaut wird
- [ ] Skills patchen (6 Referenzen): `multi-backend-asr/crispasr-server-pitfalls.md`, `polyschnack-webapp/change020-remote-workers-arch.md`, `vast-ai-gpu-instances/asr-benchmark-punc-persistent-logs.md`, `vast-ai-gpu-instances/qwen3-ark-diagnosis-2026-08-19.md`, `vast-ai-on-demand/secure-job-transfer-remote-workers.md`, `vast-ai-gpu-instances/asr-moonshine-pilot-result.md`

## Phase 1 — crispr-sep-Dienst
- [ ] Smoke-Test: CrispASR-Binary (Fork-Stand) `--separate` mit htdemucs + mel-band-roformer gegen 5-s-Testmix; htdemucs-Parity-Stand verifizieren
- [ ] Dockerfile `sep-service/` nach `aligner-service/`-Muster (CrispASR-Binary, Entrypoint mit HF-Auto-Download der GGUFs)
- [ ] `compose.yml`: Service `crispr-sep` (intern, Port 5100, Volume DATA/models)
- [ ] Endpoint `POST /separate` (audio, backend-Wahl; vocals.wav zurück; 422 bei leerer Ausgabe)
- [ ] CI: Build + Harbor-Push `polyschnack-asr-sep`; Mirror-Regel prüfen (GH-Actions nur Tests)

## Phase 2 — Webapp
- [ ] Settings-Feld `separate_backend` (default "none") im TranscriptionRun-Settings-Muster (099/103) + DB-Migration (Muster `sqlmodel-sqlite-migration`)
- [ ] `separate_client.py` (analog AlignerClient): Upload, backend, vocals-Rückgabe
- [ ] `service.py`: optionaler separate-Schritt vor ASR; Fehlerpfad → Original-Audio + ehrlicher Status
- [ ] ETA: separate-Zeit in Schätzung einbeziehen (eta.py-Muster)
- [ ] UI: Settings-Feld (Select none/htdemucs/melband), sichtbarer Status

## Phase 3 — Tests & Verifikation
- [ ] Unit: separate_client mit Mock; Fallback-Test (crispr-sep down)
- [ ] Integration: crispr-sep gegen Testmix (beide Backends)
- [ ] ASR-WER mit/ohne separate (Gesangs-Testset)
- [ ] saisoncouplet (Recording 295): Re-Align mit separate→vocals
- [ ] 90-min-Performance: GPU vs CPU-only messen
- [ ] tsc + komplette Frontend-/Backend-Suite grün

## Phase 4 — Deploy
- [ ] Deploy-Runde auf der Box (`selfupdate && update`), compose `crispr-sep` aktiv
- [ ] Live-Test: saisoncouplet-Re-Align mit htdemucs und mel-band-roformer
- [ ] Tabs/PWA vor Tests komplett schließen (bekannte 404-Polling-Quelle)
