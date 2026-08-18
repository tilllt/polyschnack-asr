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

## Phase 2 — EU-Backends
- [ ] Worker-Wrapper (`worker/worker_wrapper.py`) für ps-asr-parakeet
- [ ] `dispatcher/backends/nebius.py` (offizielle API, EU-Regionen, Preemptible)
- [ ] `dispatcher/backends/hetzner.py` + `dispatcher/backends/verda.py`
      (Verda: öffentliche Pricing-API A6000 0,61 $/h / spot 0,305 $/h)
- [ ] Provider-Whitelist (EU-only, CLOUD-Act-Regel): Dispatcher lehnt
      nicht-EU-Provider ab
- [ ] E2E-Test: Job Box → EU-Instanz → Box (verschlüsselt), Audit-Log
- [ ] Auto-Destroy-Watchdog + Kosten-Tracking (`dispatcher/costs.py`)

## Phase 3 — ps-post + weitere EU-Backends
- [ ] ps-post-Image (crispr-diar + crispr-align kombiniert, Supervisor)
- [ ] `dispatcher/backends/scaleway.py` + `dispatcher/backends/ovhcloud.py`
- [ ] `dispatcher/backends/gcore.py` / `genesis.py` (optional)
- [ ] Tests: Backend-Unit-Tests (Mock-Anbieter), Integration mit local_backend

## Dokumentierte Ausschlüsse (CLOUD-Act-Regel)
- vast.ai, RunPod, Salad, Massed Compute, Lambda, CoreWeave, CUDO —
  US/UK-Jurisdiktion, auch mit EU-Rechenzentren/günstigen Preisen gesperrt.
