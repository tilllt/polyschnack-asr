# Design — provisioning/ (Change 085)

## Modul-Layout (Repo-Root `provisioning/`)

```
provisioning/
  __init__.py          # Version, re-exporte
  spec.py              # dataclasses: OfferSpec, LaunchConfig, BackendSpec, InstanceRef
  provider.py          # GpuProvider-ABC + PreFlightResult
  vast.py              # VastProvider (Implementierung, alle robusten Lesarten)
  provisioner.py       # Zustandsmaschine, Phasen-Timing, Retry/Report/Destroy, TTL
  scaler.py            # required_instances() + scale()-Orchestrierung (idempotent)
  cli.py               # python -m provisioning <cmd> (scale/provision/destroy/status)
  backends.py          # BackendSpec aus webapp/app/backends.yaml laden
  __main__.py
provisioning/tests/    # pytest, stdlib-only; Provider hinter Fake-Server
```

## spec.py — Dataclasses (pure)

- `OfferSpec`: gpu_classes: list[str], min_vram_gb, min_disk_gb, min_ram_gb,
  price_cap_usd_h, countries: set[str] (default EU), min_inet_down_mbps,
  min_cuda_max_good: float, max_offers: int
- `LaunchConfig`: image, tag (default latest), onstart: str, port: int,
  health_path: str, env: dict, runtype (ssh_direct), disk_gb, image_login:
  str|None (private Registry), slow_start: bool, ttl_hours: float,
  label_backend: str, label_run: str|None, ssh_pub_key
- `InstanceRef`: provider, instance_id, offer_id, gpu_name, region, dph,
  backend_label
- `PreFlightResult`: ok: bool, registry, image, http_status, detail
- `Offer`: dünner Wrapper um die Provider-Rohdaten + normalisierte Felder
  (id, gpu_name, dph_total, inet_down_mbps, disk_gb, ram_gb, vram_gb,
  cuda_max_good, geolocation, reliability2)

## provider.py — ABC (Recyclbarkeit)

```python
class GpuProvider(ABC):
    name: str
    @abstractmethod search_offers(spec: OfferSpec) -> list[Offer]
    @abstractmethod pre_flight(cfg: LaunchConfig) -> PreFlightResult   # MUSS vor rent()
    @abstractmethod rent(offer: Offer, cfg: LaunchConfig) -> InstanceRef
    @abstractmethod wait_running(ref, timeout_s, poll_s=15) -> RuntimeInfo
    @abstractmethod wait_ready(ref, health_url, timeout_s, slow: bool) -> bool
    @abstractmethod destroy(ref) -> None
    @abstractmethod logs(ref, tail=300, daemon=False) -> str
    @abstractmethod report_problem(ref, category, message) -> None  # best effort
    @abstractmethod list_instances(label_backend: str|None) -> list[InstanceRef]
```

Vertrag: `rent()` wirft `ProvisioningError` mit Typ (offer_unavailable,
invalid_config, budget); `wait_running` liefert `RuntimeInfo(url, ssh_host,
ssh_port, ports, actual_status, status_msg)`; Provider müssen idempotent
destroyen (fehlende Instanz = ok).

## vast.py — VastProvider (verifizierte Lesarten → Code)

Credential: VAST_API_KEY aus Env (Haus-Stil, nie im Code). Basis
`https://console.vast.ai/api/v0`.

1. **search_offers**: POST /bundles/ mit {gpu_name:{in:…}, rentable, verified,
   type:ondemand, num_gpus:1, order:[[dph_total,asc]]}; Filter in FESTER
   Reihenfolge: geolocation∈EU → dph≤cap → vram/ram/disk ≥ min →
   cuda_max_good ≥ min → inet_down ≥ min; Sortierung: inet_down DESC, dann
   dph ASC (deterministisch, kein Zufall). → max_offers Kandidaten.
2. **pre_flight** (PFLICHT vor rent, User-Regel 2026-08-22): Registry-Manifest-
   Check ohne Miete — ghcr: `ghcr.io/token?scope=…:pull` → tags/list (200 =
   ok; leer/401 = image_login nötig oder Paket fehlt); Docker Hub:
   auth.docker.io-Token → registry-1.docker.io manifest (200); Harbor:
   service/token → /v2/…/manifests. Ergebnis als PreFlightResult.
3. **rent**: PUT /asks/{offer_id}/ (NICHT POST /asks/ → 404). Body:
   {offer_id, image, disk, runtype:ssh_direct, env:{f"-p {port}:{port}":"1"},
   onstart, duration, ssh_pub_key, cancel_unavail:true, image_login?}.
   **`new_contract` kann dict ODER int sein** → robust parsen.
4. **wait_running**: GET /instances/{id}/ — **`instances` kann Liste ODER
   dict sein** → normalisieren. Erst-Check ab 240 s (große Images), Raise
   nach **3 aufeinanderfolgenden unveränderten Daemon-Logs** (silent
   strikes, „Pull hängt") → report „Instance Takes Too Long To Load" +
   destroy + nächster Kandidat. `status_msg` mit Pull-Fortschritt loggen.
   `public_ipaddr` merken → BAD_IP-Filter für Folgerunden (gleiche IP =
   gleiche kaputte Maschine).
5. **RuntimeInfo**: ssh_host/ssh_port IMMER aus der Instanz-API lesen
   (rotiert), nicht hartkodieren; `ports` kann null sein obwohl running →
   bis ~15 min nach running warten.
6. **wait_ready**: Health-Check gegen `http://<public_ip>:<HostPort><path>`;
   bei `slow_start` KEINE Frühdiagnose (Port minutenlang zu = Modell lädt),
   warten bis MAX_READY_WAIT (2400 s Default).
7. **destroy**: DELETE /instances/{id}/; nicht existierende Instanz = ok.
8. **report_problem**: PUT /machines/{machine_id}/report/ (POST → 404!),
   erlaubte Kategorien exakt („Instance Takes Too Long To Load",
   „Unable To Start Instance", „Machine Has Port Issues", …), Rate-Limit
   3/h respektieren (429 → loggen, retry später).
9. **logs**: PUT /instances/request_logs/{id}/ (NICHT /logs/ → 404), tail +
   daemon_logs-Flag, result_url nach ~5–8 s abrufen.

## provisioner.py — Zustandsmaschine + Disziplin

- Zustände: `pending → pre_flight → renting → provisioning (pull) →
  running → ready → measuring/done | failed` — jeder Übergang mit
  ISO-Timestamp (iso_utc(), Change-081-Stil), Phasen-Deltas wie
  start_timing_vast (rent_request→rent_confirmed→instance_running→
  ssh_ready→service_ready→destroyed).
- **Ablauf pro Versuch**: pre_flight (ok?) → search → rent (Fehler →
  nächster Kandidat) → wait_running (Timeout → report+destroy+nächster) →
  wait_ready (Timeout → report+destroy+nächster) → fertig.
- **TTL**: Instanz-Label + `destroy_after`-Timestamp (ttl_hours); Provisioner
  prüft bei jedem Aufruf (und CLI `status`) und destroyed überfällige —
  kein Leak, kein Stop (nur Destroy, Kosten-Disziplin).
- **finally-Destroy** für Testläufe (frische Instanz je Test); Reuse-Modus
  (`--keep`) für Orchestrierungen, die mehrere Messungen auf einer Instanz
  machen (backend_benchmark_full --instance).
- Phasen-Logging in `prov_logs/<run_id>.jsonl` (append, jsonl) —
  deterministisch auswertbar, kein grep auf Prosa.

## scaler.py — Bedarf → Instanzen (pure + Orchestrierung)

- `required_instances(queue_len: int, concurrency: int, max_queue: int,
  min_instances: int = 1, max_instances: int = 8) -> int` — reine Funktion:
  deckt Queue bei erlaubter Warteschlange (max_queue) ab; Beispiel:
  concurrency=1, max_queue=2 → queue 0-2 → 1 Instanz; 3-4 → 2; 5-6 → 3 …
  geklemmt auf [min, max]. Unit-getestet.
- `scale(provider, backend_spec, desired: int, launch: LaunchConfig) ->
  ScaleReport` — idempotent: Ist = provider.list_instances(label=backend)
  mit status running/ready; Delta>0 → provision n Instanzen (parallel bis
  max_concurrent); Delta<0 → destroy nur idle/fertig (nie mitten im Job;
  Marker via Label phase=idle|busy).
- CLI: `python -m provisioning scale ps-pk-onnx --to 3` oder
  `--queue 7 --concurrency 1` (berechnet required_instances); `--provider
  vast` (default), `--dry-run` (zeigt Soll/Ist ohne Aktion).

## backends.py

Lädt `webapp/app/backends.yaml` (YAML: stdlib nicht vorhanden → kleine
Subset-Reader-Funktion ODER PyYAML nur im Test-Pfad; Fallback: JSON-Export
aus der Webapp). Felder: requires (vram/ram/disk) → OfferSpec; port,
health_url, compose_profile → LaunchConfig-Defaults. Keine neuen
Laufzeit-Abhängigkeiten.

## Tests (TDD, pytest)

- `test_spec.py`: Offer-Normalisierung (instances/list-dict, new_contract-
  Parse, Mbps÷1024, compute_cap÷100).
- `test_provisioner.py`: Zustandsmaschine mit FakeProvider (Scripted-Fake:
  vordefinierte Sequenzen ok/fail/timeout) — Retry zählt, Destroy im
  finally, TTL-Überfall-Destroy, Phasen-Log-Format.
- `test_scaler.py`: required_instances-Tabelle (Randfälle: queue 0, negativ,
  max clamp), scale-Idempotenz (2× scale auf 3 = 0 neue Mieten), nur-idle-
  Downscale.
- `test_vast.py`: Fake-HTTP-Server (http.server stdlib) mit den realen
  API-Antwortformen (instances als dict UND list, new_contract als dict UND
  int, 404-Meldungen, silent-strike-Logs) — kein Live-API nötig.
- `test_cli.py`: dry-run-Ausgabe, Argument-Parsing.

## Selbstlernende ETA — Ökonomie-Fundament der Autoprovisionierung

**Warum zuerst:** Jede Skalierungs- und Rentabilitäts-Entscheidung rechnet mit
GPU-Zeit = Σ audio_s × RTF(backend). Eine statische RTF-Tabelle (Stand
eta.py, Benchmark 22.08.) wird durch Betriebslast, CPU/GPU-Unterschiede und
Backend-Updates falsch → Provisioning müsste raten. Der Learner liefert die
**gelernte** Rate + ehrliche Spanne (Anti-Fake-Regel bleibt: None statt
geratenem Wert).

**Datenquelle (phasen-granular, nicht Gesamtzeit!):** `processing_ms` allein
kann die Faktoren nicht trennen (Job = Summe der Phasen). Die Pipeline misst
deshalb an den **Phasen-Grenzen** (service.py: VAD-Trim → ASR → Align →
Diar → Enhance → Punc/Truecase) je Phase eine Zeit und speichert
`phase_times_ms: dict[str, float]` im Recording (neues Feld, Auto-Migration).
Stichprobe je **Schlüssel (Phase, Variante)**:
- `asr:<backend>` (je Backend — unterschiedlich schnell)
- `vad` (VAD-Trim; Schlüssel vorbereitet für VAD-Methoden)
- `align` — **NICHT dauer-bezogen**: der Aligner skaliert mit Gruppen
  (MAX_ALIGN_GROUP_S) → lernt `ms_per_group`, Vorhersage
  `ceil(duration_s / max_group_s) × ms_per_group`
- `diar:<methode>` (energy | foxnose | pyannote)
- `enhance:<level>` (off | light | medium | aggressive)
- `noise_reduce` (ffmpeg pre-processing)
- `punc_truecase` (Post-Prozess, ps-post)

**Mechanik (`rtf_learner.py`, pure + testbar):**
- `ingest(phase_key, sample_ms, duration_s)` → interne Historie
  (letzte N=50 je Schlüssel)
- `estimate(phase_key) -> (factor, low, high, n) | None`:
  - n ≥ `N_MIN=10`: Trimmed-Mean (10 % getrimmt, Ausreißer-Schutz gegen
    Retries/Lastspitzen) über die letzten Stichproben; Spanne aus
    MAD/Perzentilen (p10–p90) statt fixem ±30 %
  - n < N_MIN: Fallback auf statische Tabelle (`ASR_RTF`, `DIAR_RTF`,
    Overhead-Werte), größere Spanne (±50 %), `n` wird mitgeliefert
  - kein Eintrag (unbekannte Phase/Variante, keine Daten): `None` — Anti-Fake
- **Invalidierung:** Backend-Bild-Update (Digest-Wechsel) setzt gelernte
  Werte zurück (Re-Evaluation, Projektziel Change 021); Admin-Reset-Endpunkt.
- **Persistenz:** neue Tabelle `rtf_estimates` (phase_key PK, sample_count,
  rtf, spread_low, spread_high, digest, updated_at) — Auto-Migration wie
  Change-082-Feld (ALTER TABLE), überlebt Neustarts.

**Kopplung an Provisioning (085):**
- `estimate_eta_s` summiert künftig **alle aktiven Phasen**:
  `Σ duration_s × factor(phase)` (VAD/ASR/Enhance/NoiseReduce dauer-bezogen,
  Align gruppen-bezogen, Diar dauer-bezogen je Methode) — gelernt > Tabelle
  > None je Phase; fehlt eine Phase → None (Anti-Fake, keine Teilschätzung
  als Ganzes)
- Autoprovisionierung rechnet mit **Spanne**: konservative Entscheidung
  (obere Grenze: genug Instanzen, um SLA zu halten), Kostenprognose mit
  unterer/oberer Grenze
- Scheduler loggt Prognose vs. Realität (geschätzte vs. tatsächliche
  GPU-Zeit je Skalierungs-Episode) → Kalibrierung kontinuierlich belegbar
- Scanner-Test (wie Change 081): keine neuen statischen RTF-Hartkodierungen
  außerhalb der Fallback-Tabelle

## Monetarisierung + Credits — Provisioning-Signal (Change 085)

**Kostenberechnung (Betreiber-Selbstkosten, deterministisch):**
- **Zwei getrennte Schichten** (nicht vermischen): der rtf_learner liefert
  nur ZEIT-Faktoren; die KOSTENSÄTZE kommen aus der Costing-Schicht
  (`costing.py`), da sie extern bestimmt sind (Strompreis, Provider-Tarife,
  Abschreibung) und nicht aus Laufzeiten gelernt werden können:
  - `provider_dph`: live vom Provider (provisionierte Instanz)
  - `local_eur_per_min`: backends.yaml `cost_per_minute_eur` (KI-Box:
    Strom + Abschreibung + Wartung) — konfiguriert, zu befüllen
  - `api_eur`: externe Dienste (LLM-Enhance) — Anbieterpreise
  - `fixed_monthly`: WebApp/Postgres/Hosting — Monatsfixkosten, NUR als
    Umlage in die Preis-Marge, NIE in Job- oder Skalierungs-Kosten
- `kosten(job) = Σ_Phasen zeit_phase(gelernt) × satz_phase`:
  - GPU-Phasen (ASR auf Instanz): `duration_s × rtf(asr:<backend>)` ×
    Provider-`dph` (live aus der Instanz) → EUR
  - Lokale Phasen (VAD/Align/Diar/Punc, lokale Box): `local_eur_per_min`
    je Backend/Phase aus backends.yaml
  - Optional LLM-Enhance: `api_eur` (nur wenn aktiv)
- Provisioning-Entscheidung rechnet NUR mit den **marginalen** Kosten
  (Instanz + Strom während des Jobs); Fixkosten = Margen-Thema.

**Exakte Kostenvoraussage für User (ehrlich):**
- Beim Upload: „voraussichtlich **X–Y Credits**" (Median ± Spanne aus den
  gelernten Faktoren) + geschätzte Dauer. „Exakt" nur als Spanne möglich —
  Anti-Fake-Regel; nach Abschluss: Ist-Verbrauch + Abweichung sichtbar
  (Kalibrierung belegbar).
- **Reserve-System:** Erwarteter Wert wird beim Start reserviert (kein
  Negativ-Konto); nach Abschluss Delta-Buchung (reserve − ist). Damit ist
  die Provisionierungs-Entscheidung auf harte Zahlen gestellt.

**Credit-/User-Modell:**
- `User` + `credit_balance` (Cent-Granularität) + `tier` (free|paid);
  `credit_transactions` (topup|usage|refund, amount, rec_id, ts)
- Free-Tier: Monatskontingent, lokale Backends, Warteschlange; Paid:
  Credits kaufen, GPU-Burst-Priorität

**Auto-Provisionierung mit Credits/zahlenden Usern:**
- **Priorisierung:** Queue sortiert nach `effective_value` — paid-Jobs (mit
  gedeckter Credit-Reserve) zuerst; Free-Jobs nur auf lokale Kapazität
- **Rentabilitäts-Gate (monetär):** GPU-Instanz wird provisioniert, wenn
  `Σ credit_value(priorisierte Queue) ≥ instanzkosten_pro_stunde ×
  min_rentability_factor` ODER `max_wait_minutes` eines **paid**-Jobs
  droht → dann Pflicht (Kundenbindung > Momentanmarge)
- **Budget-Cap:** monatliches Provisionierungs-Budget (EUR) — stoppt hart
  (Safety); gespeist aus Credit-Einnahmen
- **Kosten-Journal:** jede Skalierungs-Episode loggt erwartete Einnahmen
  (Credit-Wert) vs. erwartete Instanzkosten → „rentiert sich" wird messbar
  belegt statt behauptet
- **Admin-Parameter (DB, GUI):** `credit_per_audio_minute` je Backend/
  GPU-Klasse, `price_margin` (z. B. 2,5×), Tier-Kontingente, Budget,
  `min_rentability_factor` — gleicher Settings-Block wie Provisioning

## Admin-Backend & GUI — Steuerzentrale (Change 085)

**Persistente Settings-Schicht (neu, Basis für alles):**
- Tabelle `admin_settings` (key PK, value JSON, updated_at, updated_by) —
  Auto-Migration; Defaults im Code als Pydantic-Blöcke; PUT validiert
  (ungültige Werte → 422 mit Detail, keine stillen Fehler).
- Blöcke (Admin steuerbar, DB-persistiert):
  - `ProvisioningSettings`: enabled, provider, gpu_classes, price_cap_usd_h,
    queue_threshold, max_wait_minutes, idle_ttl_minutes, cooldown_minutes,
    max_instances_total, max_instances_per_backend, min_rentability_factor,
    budget_monthly_eur, warm_pool_count
  - `MonetizationSettings`: credit_per_audio_minute (je Backend/GPU-Klasse),
    price_margin, free_tier_monthly_credits, reserve_enabled
  - `CostingSettings`: local_eur_per_min (je Backend/Phase), api_eur,
    fixed_monthly_eur

**Router (alle `require_admin`, prefix `/api/admin`, jede Schreibaktion mit
Audit-Eintrag — wer/was/wann):**
- `GET/PUT /provisioning/settings` · `GET/PUT /monetization/settings` ·
  `GET/PUT /costing/settings`
- `GET /provisioning/status` — Ist/Soll-Instanzen je Backend, laufende
  Jobs, Kosten heute/Monat, Budget-Rest, letzte Episoden
- `POST /provisioning/scale` — manuell {backend, to|queue, concurrency,
  dry_run} → scale()
- `POST /provisioning/destroy` — {instance_id} (nur idle)
- `GET /learner/estimates` — gelernte Faktoren je Phase (rtf, Spannen, n,
  digest) · `POST /learner/reset` — {phase_key?|all}
- `GET /credits/users` — Salden, Tier, Monatsverbrauch ·
  `POST /credits/topup` {user_id, amount, reason} · `PUT /credits/user/{id}/tier`
- `GET /journal` — Skalierungs-Episoden (Einnahmen vs. Instanzkosten,
  Prognose vs. Ist) · `GET /audit` — Änderungs-Log

**Scheduler (Cron, nicht Request-Pfad):**
- `python -m provisioning schedule` (alle 2–5 min): liest Settings + Queue
  aus der DB, wendet Entscheidungsfunktion an, ruft Provisioner; Ergebnis
  (Entscheidung + Begründung + erwartete Kosten/Einnahmen) ins Journal.

**GUI (bestehende Admin-Seite erweitern, deine UI-Regeln):**
- Tabs: **Übersicht** (Instanzen Ist/Soll, Kosten heute/Monat als Balken,
  Budget-Rest) · **Provisioning** (Settings-Formular, manuelle Aktionen,
  Journal) · **Monetarisierung** (Preise, Marge, Kontingente, User-Credits
  + Topup) · **Kosten** (lokale Sätze, API, Fixkosten) · **Learner**
  (gelernte Faktoren mit Stichprobenzahl, Reset)
- Jede Aktion sichtbares Feedback + Fehler-Detail; Skalierungs-Progress
  echter Backend-Prozess („Instanz bootet — 3:42, Pull läuft"); keine
  Secrets im UI (Provider-Keys bleiben in .env).

**Sicherheit:** Budget-Cap hart im Provisioner (nicht nur UI); Credentials
nie über die API; Audit-Pflicht für alle Schreibzugriffe.

## Pre-Flight-Probe — Risikoabschätzung vor dem Hochfahren (Change 085)

**Ziel:** Bevor die teure Phase beginnt (Modell-Download 10–25 min + Server +
Jobs), in ≤ 60–90 s messen, ob die Instanz überhaupt taugt. Drei Risiken aus
der Praxis: falsche/kastrierte GPU (geteilt, ersetzt, Throttling),
schlechte Netzwerk-Anbindung zur Box (Job-Audio-Transfer), lahme CPU
(Preprocessing, CPU-Fallback). Die Probe läuft vom **Provisioner per SSH**
(ssh_direct) — Tools sind in den CUDA-Images vorhanden (curl, nvidia-smi,
sha256sum) → **kein Image-Change, keine neuen Abhängigkeiten**.

**Zwei Stufen:**
1. **Statisch (vor Miete, bereits vorhanden):** Offer-Filter — GPU-Klasse,
   VRAM, inet_down/up, reliability2, cuda_max_good. Erste Aussiebung.
2. **Dynamisch (neu, Zustand `probing` nach `running`, vor Modell-Laden):**
   `probe(ref) -> ProbeResult` — neue abstrakte Methode im GpuProvider-ABC:
   - **Netzwerk zur Box:** `curl -o /dev/null -w "%{speed_download} %{time_connect}"`
     einer Test-Datei von der Box (5-MB-Blob, z. B. `/api/benchmark/probe-file`)
     → `net_mbps_to_box`, `net_latency_ms`. Misst exakt den Pfad, den
     Job-Audios später nutzen (kein iperf3-Install nötig, pragmatischer).
   - **GPU-Identität (höchster Hebel):** `nvidia-smi --query-gpu=name,
     memory.total,clocks.sm,power.limit,temperature.gpu` → Abgleich mit der
     GEBUCHTEN GPU (Name/VRAM) — weicht sie ab → sofort Abbruch
     (geteilte/ersetzte GPU). Optional Mini-Compute, falls ein Benchmark-
     Binary im Image liegt (crispasr-Selbsttest) — nicht Pflicht.
   - **CPU:** `nproc` + CPU-Modell aus /proc/cpuinfo (statisch) +
     `sha256sum` über N MB (dynamisch, deterministisch, überall vorhanden)
     → `cpu_score_mbps`.
- **Bewertung:** Schwellwerte aus Settings (`ProbeSettings`:
  `min_net_mbps_to_box`, `max_net_latency_ms`, `min_cpu_score_mbps`,
  `gpu_identity_check`). Unterschritten → Report („Machine Performance Is
  Less Than Expected") + Destroy + nächster Kandidat — dieselbe
  Retry-Schleife wie Pull-Hangs.
- **Ökonomie:** Probe ≈ 60–90 s ≈ < 0,01 $ Instanzkosten — billiger als ein
  20-min-Modell-Download auf einer untauglichen Maschine; Grenzwert:
  Probe nie länger als 120 s (hatter Abbruch).

**Models ins Image (Build statt Boot — vast-Abrechnung belegt, Billing-FAQ
2026-08-22):** vast rechnet ab der Miete („charged for every second your
instance is in the active/connected state") — Image-Pull, Boot UND
Modell-Download laufen auf voller dph; Storage läuft in jedem Zustand,
Bandwidth pro Byte. Konsequenz:
- Backend-Images enthalten die Modelle (GGUF in den Build, nicht onstart-
  wget von HF) → bezahlte Instanz-Zeit wird zu unbezahlter Build-Zeit
- Registry-Verteilung + Host-Docker-Cache: wiederkehrende Miete (Known-
  Good-Katalog) = Pull fast gratis → Cache-Boost ist der primäre
  Boot-Beschleuniger; große Images (>2 GB) über Harbor (Skill-Regel)
- Deterministisch: Modell-Version steckt im Image-Digest (rtf_learner-
  Invalidierung passt dazu)
- **Bandwidth-Kosten** (Job-Audio Box↔Instanz, hostabhängig) in die
  Kostenformel aufnehmen (Offer-Feld inet/bandwidth-Rate)

**ENTSCHEIDUNG (User-OK 2026-08-22): Modelle ins Image — ALLE Backends.**
Begründet durch Rechnung mit echten Messwerten (22.08.-Läufe, 3090 @
0,25 $/h): große Modelle (voxtral 4,7 GB / ark 3,2 GB / qwen3 ~1,4 GB)
sparen 0,02–0,05 $ + 6–12 min Wartezeit pro Miete (74 % bei voxtral);
kleine Modelle (≤1 GB) sind monetär neutral (±0,01 $), gewinnen aber
Konsistenz + Determinismus + kein wget-Hang. Der Status-quo-onstart-wget
(single-stream, gemessen ~7 MB/s) entfällt komplett; paralleler HF-Download
(aria2c) bleibt als dokumentierter Kaltstart-Fallback. Break-even ≈ 1. Miete
(CI-Build läuft ohnehin).
- **Journal:** ProbeResult je Instanz wird geloggt (Basis für künftige
  Schwellwert-Kalibrierung und Host-Blacklist, z. B. BAD_HOST-Liste
  automatisch aufbauen).

## Known-Good-Katalog — Instanz-Historie als Sortier-Input (Change 085)

**Ziel:** Jede gemietete Instanz hinterlässt ihre Historie (Probe, Pull-Zeit,
Jobs, Erfolg/Fehler). Beim nächsten Suchen werden bekannte **gute** Hosts
bevorzugt, bekannte schlechte automatisch ausgefiltert — und derselbe Host
wiedergebucht hat den **Cache-Vorteil**: warme Docker-Layer (Image-Pull in
Minuten statt Hängen) und ggf. Modell-Reste. Die Entscheidung bleibt
deterministisch (Historie ist ein strukturierter Input, kein Raten).

**Tabelle `host_catalog` (Admin einsehbar, nur intern):**
- Identität: `machine_id`, `public_ipaddr`, `geolocation`, `gpu_name`,
  `offer_id` (letzter)
- Leistung: `probe_result` (net_mbps, latency, cpu_score, gpu_ok — letzte),
  `pull_time_s` (Boot/Provisionierung), `jobs_processed`, `jobs_ok`
- Bewertung: `reliability_score` (Erfolgsquote, gewichtet letzte N),
  `known_good: bool`, `bad_since` (Zeitstempel, wenn auf Bad-Liste),
  `last_seen`, `fail_reason` (letzter Fehler: pull_hang | oci_fail |
  probe_fail | timeout | none)

**Sortierung in search_offers (deterministisch, fester Rang):**
1. `bad_hosts` (reliability < Schwelle ODER 2+ Fehlschläge) → **ausfiltern**
   (automatische BAD_HOST-Liste, manuell resettbar über Admin)
2. `known_good` + gleiche `machine_id` wie letzter Erfolg → **Cache-Boost**
   (warme Docker-Layer), zuerst
3. `known_good` (sonst) → zweite Reihe
4. unbekannt → neutral (bestehende inet_down-Sortierung)
5. Konfigurierbar: `prefer_recent_hosts: bool` (Cache-Priorisierung an/aus)

**Cache-Befund (recherchiert 2026-08-22, offiziell):** Das vast-Repo
`vast-ai/base-image` bestätigt wörtlich: „Vast.ai host machines cache
commonly-used Docker image layers … only the smaller top layers need to be
downloaded. Result: Fast startup times." Der Cache ist der Docker-Layer-Cache
der Hosts (über beliebte Basis-Layer wie nvidia/cuda + wiederholte eigene
Mieten), kein expliziter Wieder-Miete-Mechanismus. **Build-Regel für
Backend-Images:** auf große beliebte Basis-Images aufbauen (nvidia/cuda —
unsere CrispASR-Images tun das bereits), GGUF als eigener Top-Layer.
**Empirische Validierung:** `pull_time_s` je Miete in den Katalog schreiben —
nach wenigen Mieten belegt die Messung den Cache-Effekt (wiederholte
machine_id ⇒ Pull-Zeit sinkt) statt ihn zu behaupten.

**Pflege:** Jede Skalierungs-Episode aktualisiert den Katalog (ProbeResult +
Pull-Zeit + Job-Ergebnis). Fehlgeschlagene Hosts werden erst nach
`bad_host_cooldown_hours` (Settings) wieder zugelassen. Kein User-Zugriff —
Betriebsdaten (IPs), nur Admin + Provisioner.

## Deployment / Betrieb

- Paket lokal im Repo (kein Docker-Image nötig): `python3 -m provisioning
  scale …` auf dem Admin-Host; Cron-Variante für Bedarfs-Skalierung
  (Queue-Tiefe aus Box-API lesen: GET /api/recordings?status=queued →
  required_instances → scale). Box-API-Zugriff über POLYSCHNACK_API_KEY_TILL.
- EU-Provider: Folge-Changes implementieren `GpuProvider` (Nebius/Hetzner/
  Scaleway/OVH/Gcore) — Interface + Vertrag sind der Recyclings-Punkt.
- Skill-Update: `vast-ai-gpu-instances` verweist künftig auf
  `provisioning/vast.py` als Referenzimplementierung statt Prosa-Regeln
  (Prosa bleibt als „warum", Code ist „wie").
