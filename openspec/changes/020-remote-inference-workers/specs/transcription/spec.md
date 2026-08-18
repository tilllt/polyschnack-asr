## ADDED Requirements

### Requirement: Audio-Daten verlassen die Box nur verschlüsselt

- **Ablauf:** Für jeden Job erzeugt die webapp einen Einmal-Schlüssel
  (AES-256-GCM, 256 Bit). Das Audio wird vor dem Versand verschlüsselt; auf
  dem Worker wird ausschließlich in einem tmpfs-Mount (RAM) entschlüsselt —
  Klartext berührt nie das Instance-Dateisystem. Ergebnisse werden mit
  demselben Schlüssel verschlüsselt zurückgegeben. Der Schlüssel wird beim
  Instanz-Start per Environment injiziert (nie im Image, nie auf Disk) und
  nach Jobende rotiert.
- **Warum:** Fremde Inferenz-Hardware (vast.ai, Nebius) darf die
  Transkriptionsdaten nur als Chiffre sehen; ein Host, der die Instance-Disk
  liest, findet ausschließlich Ciphertext; Instance-Diebstahl ist wertlos.
- **Architektur:** `worker/crypto.py` (gemeinsamer Code für ASR- und
  ps-post-Images), webapp (Verschlüsselung + Key-Verwaltung).

#### Scenario: Job über vast.ai-Instanz

- **Akteure:** User lädt eine Aufnahme hoch; Queue plant den Job ein.
- **Eingaben:** Audio (WAV) + Job-Schlüssel (nur im RAM/Env der Instanz).
- **Ergebnis:** Auf der Instance-Disk existiert zu keinem Zeitpunkt
  Klartext; das Ergebnis (Hypothese bzw. Segmente) kommt verschlüsselt an
  die Box zurück. Audit-Log enthält Instance-ID, Region, Zeitfenster,
  SHA-256-Hashes.

### Requirement: Drei Rollen statt All-in-One-Worker

- **Ablauf:** Die Pipeline besteht aus zwei Remote-Stufen mit getrennten
  Images: (1) `ps-asr-<backend>` — genau ein ASR-Modell je Image, GPU-Klasse
  small (12 GB, z. B. RTX 3060/4070), liefert Hypothese + Wort-Timestamps;
  (2) `ps-post` — Diarization + Aligner in einem Image (Supervisor: zwei
  Prozesse), GPU-Klasse medium (16–24 GB, z. B. A4000/3090), liefert
  Segmente mit Sprechern. Die webapp bleibt lokal und übernimmt
  Orchestrierung und Verschlüsselung.
- **Warum:** Diar/Align ist modell-unabhängig und existiert dadurch genau
  einmal statt in jedem ASR-Image; schlanke ASR-Images erlauben die
  günstige 12-GB-GPU-Klasse; Stufen können unabhängig skaliert werden.
- **Architektur:** Images aus den bestehenden Builds abgeleitet
  (ASR-Backends einzeln, crispr-diar + crispr-align zu ps-post kombiniert).

#### Scenario: Zweistufiger Job

- **Akteure:** Queue, Dispatcher, eine ASR-Instanz, eine ps-post-Instanz.
- **Eingaben:** Job-Paket Stufe 1 (Audio-Chiffre), Job-Paket Stufe 2
  (Audio-Chiffre + Hypothese-Chiffre).
- **Ergebnis:** Stufe 1 gibt Hypothese zurück, Stufe 2 daraus die fertigen
  Segmente; beide Stufen laufen auf unterschiedlichen GPU-Klassen.

### Requirement: Dispatcher mit Provider-Abstraktion

- **Ablauf:** Ein `InferenceBackend`-Protokoll kapselt Instanz-Suche, -Miete,
  -Ready-Wait, Job-Submit/-Poll und -Destroy. Erste Implementierungen:
  `local` (die Box selbst — Jobs laufen lokal wie heute), `vast` (API v0,
  EU-Region-Filter, image_login für private Registry, Destroy per DELETE),
  `nebius` (offizielle Compute-API, EU-Regionen). Konfiguration je Provider:
  Region-Whitelist (EU/EWR), Preis-Cap, GPU-Klassen-Mapping
  (small/medium/large), max. Instanzen, Warm-Pool-Größe, Monatsbudget.
- **Warum:** Skalierung darf nicht an einen Anbieter gekoppelt sein;
  Datenklassen (internal/critical) steuern, welcher Provider überhaupt in
  Frage kommt; die lokale Box als erstes Backend macht den Dispatcher sofort
  im Ist-Betrieb nutzbar (Queue/Router), ohne Verhaltensänderung.
- **Architektur:** `dispatcher/` (backends/, scheduler.py, costs.py).

#### Scenario: Engpass auf der lokalen Box

- **Akteure:** Dispatcher, local_backend, vast_backend (EU-Filter aktiv).
- **Eingaben:** Queue-Tiefe über Schwelle, Monatsbudget unterschritten.
- **Ergebnis:** Dispatcher startet eine vast-Instanz (kleinste passende
  GPU-Klasse, EU-Region, Preis-Cap), routet Jobs dorthin und destroyt sie
  nach Pool-Lebensdauer; alle Transfers bleiben verschlüsselt.

#### Scenario: Kritische Kundendaten (data_class=critical)

- **Akteure:** Dispatcher, Konfiguration (Provider-Whitelist).
- **Eingaben:** Job mit Datenklasse `critical`.
- **Ergebnis:** Nur Provider aus der Critical-Whitelist (z. B. `local` oder
  `nebius` mit AVV/EWR-Garantie) werden verwendet; vast wird für diesen Job
  ausgeschlossen; das Audit-Log dokumentiert den gewählten Provider.

### Requirement: Instanz-Hygiene und Kosten-Tracking

- **Ablauf:** Instanzen werden nach Pool-Lebensdauer per Destroy beendet
  (Regel: nie nur stoppen); ein Auto-Destroy-Watchdog mit Heartbeat begrenzt
  die Maximal-Lebensdauer auch bei Orchestrierungsausfällen. Der Dispatcher
  sammelt pro Job Provider, Region, Laufzeit und geschätzte Kosten
  (Preis × Stunden) und stoppt bei Überschreitung des Monatsbudgets das
  Cloud-Bursting.
- **Warum:** Kosten-Runaway und vergessene Instanzen sind die klassischen
  Fehler beim On-Demand-Betrieb (betriebliche Erfahrung 2025/26).
- **Architektur:** `dispatcher/costs.py`, Watchdog-Konfiguration.

#### Scenario: Orchestrierung fällt aus

- **Akteure:** Auto-Destroy-Watchdog.
- **Eingaben:** Heartbeat älter als Schwelle (z. B. 90 min), Instanz läuft.
- **Ergebnis:** Watchdog zerstört die Instanz direkt per Provider-API
  (DELETE) und alarmiert; die Instanz kann nicht „ewig" weiterlaufen.
