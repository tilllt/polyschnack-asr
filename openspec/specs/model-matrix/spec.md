# Model Matrix

## Purpose

Feature-Übersicht aller ASR-Backends und Modell-/Download-Verwaltung für die
Admin-GUI und API-Consumer.

## Requirements

### Req 1: Matrix-Endpoint

- **Ablauf:** `GET /api/models/matrix` liefert je Backend: name, status
  (active/stopped/not-created), Features (word timestamps, streaming, async,
  noise reduction, VAD, Sprachen), Ressourcenbedarf.
- **Architektur:** `routers/models.py` + `service_registry.py`; Frontend
  `AdminPanel` (Tab „Modell-Matrix") + `RecordingCard` (Backend-Dropdown
  filtert auf `status === "active"`).

#### Scenario: Backend-Dropdown

- **Akteure:** Registrierter User.
- **Eingaben:** Transcribe-Zeile, Backend wählen.
- **Ergebnis:** Nur `active`-Backends wählbar; Default zeigt
  „Standard" (Server-Default).

### Req 2: Modell-Status & Downloads

- **Ablauf:** `GET /api/models/status` → vad_available, diarize_available;
  `POST /api/models/{vad|diarize}/download` → löst Download an (HuggingFace
  Token aus Env `HF_TOKEN`).
- **Ergebnis:** Flags bestimmen, ob VAD/Speaker-Toggles in der UI aktiv sind.

#### Scenario: VAD-Modell fehlt

- **Akteure:** Beliebig.
- **Eingaben:** `GET /api/models/status`.
- **Ergebnis:** `vad_available: false` → VAD-Toggle ausgegraut; Admin kann
  Download über das Panel anstoßen.

### Req 3: Kostenanzeige

- **Ablauf:** `cost_per_minute_eur` je Backend in der Registry; paid-Backends
  (Kosten > 0) sind für anonyme User gesperrt (siehe backend-queue Req 5).

#### Scenario: Paid-Backend in der Matrix

- **Akteure:** Anonymer User.
- **Eingaben:** Matrix abrufen.
- **Ergebnis:** Backend gelistet, aber für anon nicht wählbar (403).
