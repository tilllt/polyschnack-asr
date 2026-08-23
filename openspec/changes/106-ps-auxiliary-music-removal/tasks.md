# Tasks — Change 106 (ps-auxiliary: Rename + Music Removal)

## Phase 0 — Doku-Rename ps-post → ps-auxiliary ✅ (Commit 90778c5)
- [x] `openspec/changes/020-remote-inference-workers/proposal.md`: ps-post → ps-auxiliary
- [x] `openspec/changes/022-ps-post-punctuation/` (proposal/design/tasks/2 specs): ps-post → ps-auxiliary; Hinweis ergänzt, dass Supervisor-Container bewusst nicht gebaut wird (106-Entscheidung)
- [x] Skills patchen (6 Referenzen, inkl. Korrektur „EIN Container"-Aussage)

## Phase 1 — crispr-sep-Dienst (Code fertig, Smoke-Test läuft)
- [x] Smoke-Test `--separate`: **htdemucs-F16 separiert korrekt** (4 sources, vocals.wav); mel-band-f16 + htdemucs-q8_0 laufen noch (CPU scalar — sehr langsam, bestätigt Risiko)
- [x] Dockerfile `sep-service/` (CrispASR-Fork tilllt/CrispASR @ 2bded4194, CUDA arch 86, Entrypoint mit HF-Auto-Download beider GGUFs)
- [x] `compose.yml`: Service `crispr-sep` (intern, Port 5100, healthcheck, Volume DATA/models)
- [x] Endpoint `POST /v1/audio/separate` (multipart file+backend, vocals.wav zurück, ehrlicher 422, Ein-Job-Lock) + `GET /health` + `/status`
- [ ] CI: Build + Harbor-Push `polyschnack-asr-sep` (nach Deploy-Entscheidung)

## Phase 2 — Webapp (Code fertig, Tests laufen)
- [x] Settings-Feld `separate_backend` (default "none") in TranscriptionRun-Settings + DB-Migration (db.py ×4, models.py)
- [x] `separate_client.py` (analog AlignerClient): health/status/separate → vocals | None
- [x] `service.py`: separate-Phase zwischen Enhance und ASR; Fehlerpfad → Original-Audio + Log (ehrlich)
- [x] ETA: `SEP_OVERHEAD = 0.25` (statisch + Learner-Pfad)
- [x] UI: FeatureToggles-Select „Sep: aus/htdemucs/melband" (Re-Transcribe auf der Karte); Upload-Pfad v1 ohne Separate (PendingRecording separate:"none")
- [ ] tsc 0 ✅ / Backend-Suite / Frontend-Suite (303/303 ✅)

## Phase 3 — Tests & Verifikation (Align-Test läuft)
- [x] **Realer Align-Test (TTS-Thorsten, 12,6 s, bekannter Text):** Mix vs. vocals durch qwen3-forced-aligner — beide 30/30 Wörter, Timestamps Δ=0,005 s identisch; **vocals 3× schneller** (34,4 s vs 11,0 s CPU). Auch lauter Sines-Mix alignt 30/30 (Synthetik bricht Aligner nicht — echter saisoncouplet-Test nur auf der Box möglich)
- [ ] Unit: separate_client mit Mock; Fallback-Test (crispr-sep down)
- [ ] Integration: crispr-sep gegen Testmix (beide Backends)
- [ ] saisoncouplet (Recording 295): Re-Align mit separate→vocals **auf der Box nach Deploy**
- [ ] 90-min-Performance: GPU vs CPU-only messen (CPU: melband scalar sehr langsam — Befund)

## Phase 4 — Deploy
- [ ] Deploy-Runde auf der Box (`selfupdate && update`), compose `crispr-sep` aktiv
- [ ] Live-Test: saisoncouplet-Re-Align mit htdemucs und mel-band-roformer
- [ ] Tabs/PWA vor Tests komplett schließen (bekannte 404-Polling-Quelle)
