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

### Req 4: Serverweite Auskünfte werden einmal je Seite geholt (Change 236)

- **Ablauf:** Die Auskünfte, die für jede Aufnahmekarte gleich sind
  (Modell-Matrix, Backend-Fähigkeiten, Modell-Status, Vorlagen,
  Format-Vorgaben, Zustellziele, LLM-Adressen, Export-Vorlagen), werden über
  `src/sharedConfig.ts` (`once()`, 30 s Ablaufzeit) geteilt geholt — nicht je
  Karte. Fehler werden nicht gemerkt: der nächste Aufruf versucht es erneut.
- **Grund (gemessen 30.09.2026):** Bei 116 Aufnahmen erzeugte ein
  Seitenaufruf ~812 Anfragen in 24 s (Spitze 111/s) — Box-Last 16,
  Netzwerk-Unterbrechungen 5 % → 17,5 %, Tab ~24 s blockiert. Mit der Teilung
  sind es 8 Anfragen, unabhängig von der Zahl der Aufnahmen.
- **Architektur:** `src/sharedConfig.ts`, `src/components/RecordingCard.tsx`,
  `src/components/UploadZone.tsx`; Prüfungen `src/sharedConfig.test.ts` und
  `src/components/RecordingList.sharedConfig.test.tsx` (zählt Anfragen an der
  Netzwerk-Grenze).

#### Scenario: Liste mit vielen Aufnahmen

- **Akteure:** Registrierter User.
- **Eingaben:** Aufnahmenliste mit 100+ Aufnahmen öffnen.
- **Ergebnis:** Jede serverweite Auskunft wird genau einmal geholt; die Zahl
  der Anfragen wächst **nicht** mit der Zahl der Karten.
- **Gegenprobe:** Ohne die Teilung (Ablauf-Treffer in `once()` stillgelegt)
  werden die Prüfungen rot.
