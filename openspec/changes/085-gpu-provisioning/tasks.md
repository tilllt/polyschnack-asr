# Tasks — Change 085 (GPU-Provisioner)

Reihenfolge = Abhängigkeiten; Tests begleiten jeden Schritt (TDD).

## 0. Selbstlernende ETA (Ökonomie-Fundament, zuerst!)
- [ ] service.py: **Phasen-Zeitmessung** an den Pipeline-Grenzen
      (VAD/ASR/Align/Diar/Enhance/NoiseReduce/Punc) → `phase_times_ms`-Feld
      (Auto-Migration) + Stichproben-Ingest beim Job-Abschluss
- [ ] `rtf_learner.py` (pure): ingest/estimate je **Schlüssel
      (Phase, Variante)** — asr:<backend>, diar:<methode>, enhance:<level>,
      vad, align (ms/Gruppe), noise_reduce, punc_truecase; Trimmed-Mean,
      MAD-Spanne, N_MIN-Fallback, None-Anti-Fake, Digest-Invalidierung
- [ ] `test_rtf_learner.py`: Trimmed-Tabelle, Ausreißer, n<10-Fallback,
      unbekannte Phase, Digest-Reset, Align-Gruppen-Modell
- [ ] models/crud: `rtf_estimates`-Tabelle (Auto-Migration) + Persistenz
- [ ] eta.py: estimate_eta_s = **Summe der aktiven Phasen** (gelernt >
      Tabelle > None je Phase; Align gruppen-bezogen); Scanner-Test gegen
      neue Hartkodierungen
- [ ] Admin-Endpunkt: Reset + Anzeige der gelernten Werte je Phase

## 1. Doku + Grundgerüst
- [x] proposal.md (dieses Change)
- [x] design.md
- [ ] `provisioning/`-Paket anlegen (spec.py: dataclasses + Offert-Normalisierung)
- [ ] `test_spec.py`: Normalisierung (Mbps, compute_cap, new_contract-Parse,
      instances list|dict)

## 2. Provider-ABC
- [ ] `provider.py`: GpuProvider-ABC + Vertrag (Fehler-Typen, idempotentes
      destroy) + PreFlightResult
- [ ] `test_provider.py`: Vertragstests mit minimalem FakeProvider

## 3. VastProvider (Kern: alle robusten Lesarten)
- [ ] `vast.py`: search_offers (EU-Filter, Preis-Cap, Ressourcen, inet_down-
      Sortierung — deterministisch)
- [ ] `vast.py`: pre_flight (Registry-Check: ghcr/Docker-Hub/Harbor — User-
      Regel 2026-08-22)
- [ ] `vast.py`: rent (PUT /asks/, new_contract dict|int, image_login)
- [ ] `vast.py`: wait_running (silent-strike 3×, 240-s-Erst-Check, BAD_IP,
      ssh_host/Port aus API, ports-null-Toleranz)
- [ ] `vast.py`: wait_ready (slow_start ohne Frühdiagnose, 2400-s-Deckel)
- [ ] `vast.py`: destroy + report_problem (exakte Kategorien, Rate-Limit) + logs
- [ ] `test_vast.py`: Fake-HTTP-Server mit realen API-Antwortformen

## 4. Provisioner (Zustandsmaschine + Disziplin)
- [ ] `provisioner.py`: Zustände, Phasen-Timing (iso_utc), Retry
      (report+destroy+nächster Kandidat), TTL-Destroy, finally-Destroy,
      Reuse-Modus
- [ ] `test_provisioner.py`: Scripted-Fake (ok/fail/timeout-Sequenzen),
      TTL-Überfall, Phasen-Log-Format

## 5. Scaler
- [ ] `scaler.py`: required_instances (pure) + scale (idempotent, nur-idle-
      Downscale, max_concurrent)
- [ ] `test_scaler.py`: Tabellentests + Idempotenz + Downscale-Regeln

## 6. Backend-Specs + CLI
- [ ] `backends.py`: backends.yaml → OfferSpec/LaunchConfig (requires, port,
      health)
- [ ] `cli.py` + `__main__.py`: scale/provision/destroy/status, --dry-run,
      --provider
- [ ] `test_cli.py`: dry-run-Ausgabe, Argumente

## 7. Integration + Verifikation (kein Fake)
- [ ] `--dry-run` gegen echte vast-API (keine Miete): Offers + pre_flight für
      ein Benchmark-Backend
- [ ] Echter Smoke-Lauf: 1 Instanz mieten (z. B. ps-pk-onnx, kleinstes
      Modell), health abwarten, destroy — Kosten-Cap + TTL
- [ ] Skill `vast-ai-gpu-instances`: Verweis auf provisioning/vast.py als
      Referenzimplementierung ergänzen
- [ ] CI (Test-Job läuft das provisioning-Testsuite mit) + Commit + Pipeline

## 7b. Pre-Flight-Probe (Risikoabschätzung)
- [ ] Box: Probe-Datei-Endpunkt (5-MB-Blob, z. B. `/api/benchmark/probe-file`)
- [ ] provider.py: `probe(ref)` im ABC + `ProbeResult` (net_mbps, latency,
      gpu_name/vram vs. gebucht, cpu_score)
- [ ] vast.py: `probe` via SSH (curl zur Box, nvidia-smi, sha256sum) —
      harter 120-s-Deckel
- [ ] provisioner.py: Zustand `probing` (nach running, vor Modell-Laden);
      Abbruch + Report + Destroy bei Schwellwert-Unterschreitung
- [ ] Settings: `ProbeSettings`-Block (min_net_mbps, max_latency,
      min_cpu_score, gpu_identity_check) + Admin-GUI
- [ ] `test_probe.py`: Probe-Ergebnisse → Entscheidung (ok/abbruch),
      Fake-SSH-Antworten, 120-s-Deckel, Journal-Eintrag

## 7c. Known-Good-Katalog (Instanz-Historie)
- [ ] models/crud: `host_catalog`-Tabelle (Auto-Migration) + Update bei jeder
      Episode (Probe, Pull-Zeit, Jobs, Erfolg/Fehler)
- [ ] vast.py search_offers: Katalog-Rangfolge (bad raus, known_good +
      machine_id-Boost, unbekannt neutral) — deterministisch, getestet
- [ ] Settings: `prefer_recent_hosts`, `bad_host_cooldown_hours`,
      `reliability_threshold`
- [ ] Admin: Katalog-Ansicht + Bad-Liste-Reset
- [ ] `test_catalog.py`: Rangfolge, Bad-Liste-Aufbau (2 Fehlschläge),
      Cooldown-Ablauf, Cache-Boost-Logik

## 8. Monetarisierung + Credits (Provisioning-Signal)
- [ ] models/crud: `credit_balance` + `tier` (User), `credit_transactions`
      (topup|usage|refund) — Auto-Migration
- [ ] `pricing.py` erweitern: `quote_credits(job) -> (low, median, high)` aus
      rtf_learner-Faktoren × `credit_per_audio_minute` × `price_margin`;
      Anzeige vor Upload (API + UI)
- [ ] Reserve-System: Reservierung beim Job-Start, Delta-Buchung beim
      Abschluss (kein Negativ-Konto); Free-Tier-Kontingent
- [ ] Queue-Priorisierung: `effective_value` (paid + gedeckte Reserve zuerst;
      Free nur lokale Kapazität)
- [ ] Rentabilitäts-Gate monetär: `Σ credit_value ≥ instanzkosten ×
      min_rentability_factor` ODER paid-SLA; Budget-Cap (monatlich)
- [ ] Kosten-Journal je Skalierungs-Episode (Einnahmen vs. Instanzkosten)
- [ ] Tests: Quoting (Spanne, Anti-Fake), Reserve-Buchungen, Priorisierung,
      Gate-Entscheidungen, Budget-Hart-Stopp

## 10. Admin-Backend & GUI (Steuerzentrale)
- [ ] `admin_settings`-Tabelle (Auto-Migration) + Pydantic-Blöcke
      (Provisioning/Monetization/Costing) + Defaults + Validierung (422)
- [ ] Router: settings GET/PUT (3 Blöcke) mit Audit-Eintrag
- [ ] Router: `/provisioning/status` + `scale` (dry_run) + `destroy` (idle)
- [ ] Router: `/learner/estimates` + `reset`; `/credits/users` + `topup` +
      `tier`; `/journal` + `/audit`
- [ ] Scheduler: `python -m provisioning schedule` (Cron, Settings + Queue →
      Entscheidung → Journal)
- [ ] Frontend: Admin-Tabs (Übersicht mit Kosten-Balken, Formulare,
      Journal, Learner-Ansicht, User-Credits)
- [ ] Tests: Settings-Validierung, Audit, Status, Scale mit FakeProvider,
      Budget-Hart-Stopp, Scheduler-Entscheidung

## 9. Integration + Abnahme
- [ ] GUI: Monetarisierungs-/Provisioning-Settings (ein Block), Status
      (Instanzen, Kosten heute/Monat, Journal) — Balken statt Tabellen
- [ ] End-to-End: Upload → Quote → Verarbeitung (lokales Backend) →
      Abbuchung → Kalibrierung (Prognose vs. Ist)
- [ ] CI + Commit + Pipeline (alle Testsuiten)

## Abnahme-Kriterien
- Deterministisch: gleicher Input (Angebote, Fehler) → gleiche Entscheidung
  (kein Zufall in Filter/Sortierung)
- Pre-Check vor jeder Miete (pre_flight ok ODER expliziter Abbruch)
- Keine vergessene Instanz: TTL-Destroy + finally-Destroy + CLI status
- Skalierung idempotent: 2× scale(3) mietet nur einmal
- Provider-Wechsel ohne Logik-Änderung: Fake-EU-Provider (Nebius-Signatur)
  in einem Test beweist die Recyclbarkeit
- Stdlib-only (wie suite_import.py), keine neuen Deps
