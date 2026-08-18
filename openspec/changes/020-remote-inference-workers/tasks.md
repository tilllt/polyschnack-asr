# Tasks — Change 020 (Remote Inference-Worker, Konzept)

## Phase 0 — Konzept (dieser Change)
- [x] proposal.md: Rollen-Trennung, Verschlüsselung, Dispatcher-Abstraktion
- [x] specs/transcription/spec.md: Requirements + Szenarien
- [ ] OpenSpec-validieren, Commit + Push
- [ ] Bewertung mit User (GPU-Klassen, Provider-Priorität, PoC-Umfang)

## Phase 1 — PoC (nach Freigabe)
- [ ] `worker/crypto.py`: AES-256-GCM (encrypt/decrypt), tmpfs-Helfer
- [ ] PoC-Messung auf vast 3060 (EU): Parakeet laden, Testjob, VRAM-Peak +
      RTF loggen (belegt 12-GB-Eignung, gemessen statt geschätzt)
- [ ] `dispatcher/backends/base.py` + `local_backend.py` (Box = Backend)
- [ ] Queue-Stufen-Orchestrierung in webapp (Stufe 1 → Stufe 2)

## Phase 2 — Vast-Backend
- [ ] `dispatcher/backends/vast.py` (API v0, EU-Filter, image_login, Destroy)
- [ ] Worker-Wrapper (`worker/worker_wrapper.py`) für ps-asr-parakeet
- [ ] E2E-Test: Job Box → vast → Box (verschlüsselt), Audit-Log
- [ ] Auto-Destroy-Watchdog + Kosten-Tracking (`dispatcher/costs.py`)

## Phase 3 — ps-post + weitere Provider
- [ ] ps-post-Image (crispr-diar + crispr-align kombiniert, Supervisor)
- [ ] `dispatcher/backends/nebius.py` (offizielle API, EU-Regionen)
- [ ] Datenklassen-Filter (internal/critical) aktiv
- [ ] Tests: Backend-Unit-Tests (Mock-Anbieter), Integration mit local_backend
