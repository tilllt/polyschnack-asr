# Change 085 — Deterministischer GPU-Provisioner (Provider-abstrakt, skalierbar)

Status: Proposal
Datum: 2026-08-22
Autor: Hermes (Till-Auftrag)

## Goal

Das implizite vast.ai-Wissen (Provisionierungs-Pitfalls aus Skill
`vast-ai-gpu-instances` + `scripts/start_timing_vast.py`) in **deterministischen,
getesteten Python-Code** konvertieren: ein Provisioner, der GPU-Instanzen für
ASR-Backends mietet, auf Health wartet und **bei Bedarf skaliert** — über ein
**Provider-Interface**, das sich für andere GPU-Clouds recyceln lässt
(PolySchnack-Produktion: nur EU-Anbieter — Nebius/Verda/Hetzner/Scaleway/OVH/
Gcore, CLOUD-Act-Constraint; vast bleibt für Benchmark/Dev).

## Problem / Auslöser

- Provisionierungswissen lebt in Prosa (Skill-Referenzen) + einem
  680-Zeilen-Skript mit hartkodierten Annahmen. Jede neue Miete wiederholt
  manuell: Kandidaten-Filter, Pre-Check (Image pullbar), Wait-Heuristiken
  (silent strikes, slow_start), Report+Destroy+Retry, Phasen-Timing.
- Fehlerklassen aus der Praxis: privates ghcr-Image → Pull-Stall auf allen
  Instanzen (Whisper, 5× Timeout), `new_contract` als dict ODER int,
  `instances` als Liste ODER dict, ssh_host/Port-Rotation, hängende
  Image-Pulls (2× unveränderte Daemon-Logs = Host aufgeben), vergessene
  Instanzen (Stop statt Destroy).
- „Backends bei Bedarf skalieren": heute kein Mechanismus — Backends laufen
  statisch in compose; GPU-Zusatzkapazität muss manuell gemietet werden.

## Was der Mechanismus kann (v1)

1. **Deterministische Miete** (`VastProvider`): feste Filterreihenfolge
   (Region → Preis-Cap → VRAM/disk/ram/cuda → inet_down desc), Pre-Check
   der Registry (Manifest 200) VOR jeder Miete, Robustheits-Lesarten
   (new_contract/instances/ssh_host/Ports), Image-Pull-Überwachung mit
   silent-strike-Erkennung, Report+Destroy+nächster Kandidat, BAD_IP-Filter,
   Destroy im finally + TTL (kein Stop, kein Leak).
2. **Skalierung nach Bedarf**: reine Funktion `required_instances(queue_len,
   concurrency, max_queue)` + `scale(backend, desired)` — idempotent über
   Backend-Labels (Ist-Zustand = laufende Instanzen mit Label; Soll-Zustand
   aus CLI/Cron). Runter-Skalieren nur im idle-Zustand.
3. **Provider-Abstraktion**: `GpuProvider`-ABC (search/rent/wait_running/
   wait_ready/destroy/logs/report/pre_flight). `VastProvider` = erste
   Implementierung; EU-Provider (Nebius/Hetzner/…) als Folge-Changes über
   dasselbe Interface.
4. **Backend-Specs aus backends.yaml**: `requires` (vram/ram/disk) →
   OfferSpec; kein Duplizieren der Backend-Metadaten.

## Nicht-Ziele (v1)

- Kein Auto-Scaling-Controller im Webapp-Prozess (erst CLI + Cron-taugliche
  deterministische Entscheidung; Event-getrieben später).
- Kein Multi-Provider-Failover/Spot-Märkte/Kubernetes.
- Kein Produktions-Deploy auf US-Clouds (EU-Constraint bleibt).
- Kein Persistieren von Credentials (nur /opt/data/.env, Haus-Stil).

## Entscheidung

Provider-Interface + VastProvider + Provisioner + Scaler als eigenständiges
Python-Paket `provisioning/` im Repo (stdlib wie `benchmarks/import/
suite_import.py`, keine neuen Abhängigkeiten). Pure Logik (Filter, Sortierung,
Skalierungsfunktion, Zustandsmaschine) strikt testbar; Provider-API hinter
Fake-Server in Tests. Backend-Specs kommen aus `webapp/app/backends.yaml`
(single source of truth).
