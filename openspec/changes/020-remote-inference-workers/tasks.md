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

## Phase 2 — Stufe-1-Backends (günstig, verschlüsselt)
- [ ] Worker-Wrapper (`worker/worker_wrapper.py`) für ps-asr-parakeet
- [ ] `dispatcher/backends/vast.py` (API v0, Bundles-Suche, image_login,
      Destroy per DELETE, Auto-Destroy-Watchdog)
- [ ] `dispatcher/backends/theta.py` (Theta EdgeCloud GPU-Compute API)
- [ ] Datenklassen-Filter (internal/critical) + Modus-Konfiguration
- [ ] E2E-Test: Job Box → vast/Theta → Box (verschlüsselt), Audit-Log
- [ ] Auto-Destroy-Watchdog + Kosten-Tracking (`dispatcher/costs.py`)

## Phase 3 — ps-post + Stufe-2-Backends (EU-only, wenn Konzept steht)
- [ ] **Messpunkt Align-CPU:** RTF-Vergleich qwen3-forced-aligner (ggml)
      auf derselben Testaufnahme: CPU vs. CUDA × f16 vs. q4-k-m (OpenVoiceOS-
      Quantisierung, ~1 GB statt 1,8 GB; Community-Parität laut Perplexity-
      Recherche 2026-08-18) — entscheidet, ob ps-post auf CPU-only-Instanzen
      laufen kann und ob die quantisierte Variante reicht (Qualität an
      Wortgrenzen mitmessen, nicht nur RTF). Bis dahin ps-post mit
      optionaler small-GPU. Lizenz-Hinweis: Seamless (deutsch-besser) ist
      CC-BY-NC → NICHT kommerziell nutzbar; Qwen3 (Apache 2.0) bleibt.
- [ ] ps-post-Image (crispr-diar + crispr-align kombiniert, Supervisor)
- [ ] `dispatcher/backends/nebius.py` + `dispatcher/backends/verda.py`
      (Verda: öffentliche Pricing-API A6000 0,61 $/h / spot 0,305 $/h)
- [ ] `dispatcher/backends/hetzner.py` + `dispatcher/backends/scaleway.py`
      + `dispatcher/backends/ovhcloud.py`
- [ ] EU-only-Modus: sperrt alle Nicht-EU-Backends global; Pflicht für
      `critical`-Jobs
- [ ] Tests: Backend-Unit-Tests (Mock-Anbieter), Integration mit local_backend

## Nicht vorgesehen
- RunPod, Salad, Spheron (US/LA), Massed Compute, Lambda, CoreWeave,
  TensorDock, CUDO (UK) — kein Vorteil gegenüber Stufe 1/2.
- Golem (DE) bleibt in Beobachtung (EU-Marktplatz, GPU-Angebot unreif).
