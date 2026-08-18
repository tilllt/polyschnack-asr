# Change 020 — Remote Inference-Worker: verschlüsselter Job-Transfer, Webapp/ASR/ps-post-Trennung, modularer Dispatcher

## Problem

PolySchnack läuft heute als Monolith-Stack auf einer einzigen GPU-Box
(webapp + ps-pk-onnx + crispr-diar + crispr-align, alle Container auf einer
RTX 3090 Ti, VRAM zu ~98 % belegt). Skalierung bedeutet heute: teurere/mehr
GPUs auf derselben Box — keine Option, den Engpass auszulagern. Gleichzeitig
fehlt ein Weg, Inferenz **bei Lastspitzen** auf günstige On-Demand-Hardware
auszulagern, ohne die Datensicherheit der Transkriptionsdaten zu gefährden:
Audio-Dateien sind sensible Daten, die eine fremde Instanz nur als Chiffre
sehen dürfen.

Drei Entscheidungen aus der Diskussion (2026-08-18) werden hier verbindlich:

1. **Dienst-Trennung in drei Rollen:** webapp (kein GPU-Bedarf, bleibt auf der
   Box) · ps-asr-&lt;backend&gt; (ein ASR-Modell je Image, schlank, läuft auf
   günstigen 12-GB-Karten) · ps-post (Diarization + Aligner, modell-unabhängig,
   16–24-GB-Klasse). Diar/Align existiert genau EINMAL, nicht in jedem
   ASR-Image.
2. **Ende-zu-Ende-verschlüsselter Job-Transfer:** Audio verlässt die Box nur
   als AES-256-GCM-Chiffre; auf dem Worker existiert Klartext ausschließlich
   im RAM (tmpfs), nie auf der Instance-Disk.
3. **Modularer Dispatcher:** Eine Provider-Abstraktion verwaltet Inference-
   Backends (vast.ai, Nebius, später Hetzner/Lambda) UND die lokale Box als
   erstes Backend — einheitliche Queue, EU-Region-Filter, GPU-Klassen-
   Matching, Warm-Pooling, Auto-Destroy, Kosten-Tracking.

## Lösung

### Rollen und Images

- **webapp** (lokal): Upload, Store, Queue, Verschlüsselung, Dispatcher-
  Steuerung, Router zwischen den Stufen. Kein GPU-Bedarf.
- **ps-asr-&lt;backend&gt;**: ein Image je ASR-Modell (parakeet, qwen3, ark,
  moonshine…), Modell + Runtime + Worker-Wrapper. GPU-Klasse: small
  (12 GB, z. B. RTX 3060/4070). Gibt Hypothese + Wort-Timestamps zurück.
- **ps-post**: Diarization + Aligner in EINEM Image (Supervisor: zwei
  Prozesse). GPU-Klasse: medium (16–24 GB, z. B. A4000/3090). Nimmt Audio +
  Hypothese, liefert Segmente mit Sprechern.
- **Dispatcher**: Bestandteil der webapp (oder eigener Service) — vermittelt
  Jobs an Instanzen, verwaltet Lebenszyklus, wählt Provider/Region/Klasse.

### Verschlüsselter Job-Ablauf (zwei Stufen)

1. Upload → Audio im Store → Job erzeugt → Job-Schlüssel (AES-256-GCM) wird
   pro Job generiert → Audio wird verschlüsselt; nur der Ciphertext verlässt
   die Box.
2. Dispatcher besorgt ASR-Instanz → Job-Paket {Ciphertext, Job-ID, Token}.
   Der Job-Schlüssel liegt NUR in der Instance-Env (wird beim Instanz-Start
   injiziert, nie ins Image geschrieben).
3. ASR-Worker: Paket über HTTPS+TLS holen → in tmpfs entschlüsseln → ASR →
   Hypothese + Timestamps mit demselben Schlüssel verschlüsseln → zurück.
4. webapp entschlüsselt, validiert → zweite Stufe: Dispatcher besorgt
   ps-post-Instanz → Paket {Audio-Chiffre, Hypothese-Chiffre}.
5. ps-post: entschlüsseln (tmpfs) → Diar + Align → Segmente verschlüsseln →
   zurück → webapp persistiert. Instanz gemäß Warm-Pool-Regel behalten oder
   destroyen (NIE nur stoppen).

### Dispatcher-Provider-Abstraktion

**Verbindliche Regel: NUR reine EU-Anbieter (CLOUD Act).** Zugelassen sind
ausschließlich Unternehmen mit Sitz und Infrastruktur in der EU/EWR
(„EU-Unternehmen, eigene Infrastruktur"). US-Firmen mit EU-Rechenzentren
(z. B. RunPod, Lambda, CoreWeave), US-Marktplätze (vast.ai, Salad) und
UK-Firmen (z. B. CUDO) sind ausgeschlossen — unabhängig von der
E2E-Verschlüsselung. Die Verschlüsselung entschärft das technische Risiko
(US-Behörden erhielten nur Chiffre), die EU-only-Regel macht die
Rechtslage eindeutig (kein US-Vertragspartner, keine US-Gerichtsbarkeit
über Auftragsverarbeitung).

**Begründung Vermittlung (vast.ai-Fall):** Der CLOUD Act knüpft an das
Unternehmen mit Zugriff an, nicht an den GPU-Standort. vast.ai verwaltet
die gemieteten Instanzen technisch (Portal, SSH-Proxy, Container-Lifecycle)
und ist damit ein US-„covered provider" mit Zugriffsweg auf die Instanz —
auch wenn die GPU bei einem EU-Host steht. Reale Zugriffswege (in der
Betriebspraxis verifiziert): Container-Logs per `request_logs`, SSH-Keys
per `POST /instances/{id}/ssh/`, SSH-Proxy, Lifecycle-API (Reboot/Start/
Destroy), Port-Tunnel. Kein Confidential Computing, keine Attestation.
„EU-Instanz über US-Marktplatz" ist deshalb rechtlich NICHT gleichwertig
mit „Instanz direkt bei einem EU-Anbieter" (Hetzner/Nebius/Verda/Scaleway:
kein US-Vertragspartner mit Instanz-Zugriff).

**Konsequenz für den Worker-Wrapper:** Logs auf Metadaten begrenzen
(Job-ID, Status, Laufzeit) — nie Audio-Pfade, Wort-Hypothesen oder
Job-Inhalte nach stdout/stderr, damit selbst der Log-Zugriffsweg leer
bleibt.

Interface `InferenceBackend` (Python-Protokoll):

- `list_offers(filter) -> list[Offer]` — Preis, GPU, VRAM, Region, Reliabilität
- `acquire(offer, image, disk, env) -> Instance`
- `wait_ready(instance) -> Endpoint`
- `submit_job(endpoint, job) / poll(instance, job_id)`
- `destroy(instance)` + `instance_meta(instance)` (Provider, Region, Kosten)

Implementierungen (EU-only):

- **local_backend** — die Box selbst (erstes Backend; Jobs laufen lokal wie
  heute, Dispatcher nur als Queue/Router → sofort nutzbar im Ist-Betrieb).
- **nebius_backend** — Nebius (NL, EU): offizielle API, EU-Regionen,
  Preemptible/Standard-Klassen (L40S 0,74 $/h, H100 2,15 $/h — offiziell,
  08/2026).
- **hetzner_backend** — Hetzner (DE): GPU-Server GEX-Line, RZ in DE/FI/NL,
  ISO 27001. Preise im Server-Finder zu prüfen (nicht statisch extrahierbar).
- **scaleway_backend** — Scaleway (FR, Iliad Group): L4/L40S/H100-GPU-
  Instances, RZ Paris/Marseille. Preise im Rechner zu prüfen.
- **ovhcloud_backend** — OVHcloud (FR): GPU-Instances, RZ FR.
- **verda_backend** — Verda (FI, ehem. DataCrunch): öffentliche Pricing-API
  (offiziell, 08/2026): A6000 48 GB 0,61 $/h on-demand / 0,305 $/h spot,
  L40S 1,37 $/h / 0,685 $/h spot.
- **gcore_backend** (optional) — Gcore (LU).
- **genesis_backend** (optional) — Genesis Cloud (IS, EWR — kein EU-Mitglied,
  aber EWR-Datenfluss und isländische Firma ohne CLOUD-Act-Exposure).
- **golem_backend** (Beobachtung, optional) — Golem Network (Golem Factory
  GmbH, Berlin, DE — einziger dezentraler GPU-Marktplatz mit EU-Sitz).
  GPU-Compute im Aufbau (Marketplace-Beta, eigene Runtime statt Docker),
  noch nicht produktionsreif; als Backend ergänzbar, sobald die GPU-Flotte
  und API stabil sind.

Ausgeschlossen (US/UK-Jurisdiktion, dokumentiert): vast.ai, RunPod, Salad,
Spheron (Spheron Networks, Los Angeles CA — verifiziert 08/2026), Massed
Compute, Lambda, CoreWeave, TensorDock, CUDO (UK) — auch wenn EU-Regionen
oder günstige Preise angeboten werden.

Konfiguration je Provider: Region-Whitelist (EU/EWR), Preis-Cap, GPU-Klassen-
Mapping (small/medium/large ↔ VRAM), max. Instanzen, Warm-Pool-Größe,
Monatsbudget.

### Sicherheitsprinzipien (verbindlich)

- Klartext existiert nur an zwei Orten: Store auf der Box und RAM (tmpfs) auf
  dem Worker. Alles andere ist Chiffre.
- Job-Schlüssel: Einmal-Schlüssel pro Job, Rotation nach Jobende; niemals im
  Image, niemals auf der Worker-Disk.
- Transit überall TLS; Worker-Endpoint mit Token-Auth.
- Instanz-Hygiene: Destroy nach Pool-Lebensdauer (Regel: nie stoppen),
  Auto-Destroy-Watchdog mit Heartbeat.
- Audit: pro Job Instance-ID, Provider, Region, Zeitfenster, SHA-256 des
  Audios und des Ergebnisses.
- Datenklassen: `internal` (nicht-kritisch, vast EU ok) vs. `critical`
  (Gesundheit/Recht → nur Provider mit AVV/EWR-Garantie, z. B. Nebius oder
  lokale Box).

## Betroffene Dateien (Konzeptstand)

- `dispatcher/` (neu): `backends/base.py`, `backends/local.py`,
  `backends/vast.py`, `backends/nebius.py`, `scheduler.py`, `costs.py`
- `worker/` (neu): `worker_wrapper.py` (ASR und ps-post teilen sich den
  Wrapper), `crypto.py` (AES-256-GCM, tmpfs-Handling)
- `webapp/`: Job-Queue-Erweiterung (Stufen-Orchestrierung), Key-Verwaltung,
  Audit-Log
- Images: `ps-asr-<backend>` (aus bestehenden ASR-Builds), `ps-post` (aus
  crispr-diar + crispr-align)
