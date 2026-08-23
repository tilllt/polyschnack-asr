# Change 094 — runs → results: Settings & Ergebnisse versioniert, Recording wird Stamm (Etappe 1)

**Status:** Design, Implementierung folgt
**Auslöser (2026-08-23, Diskussion mit User/Ruben):**
- „Die Felder beschreiben die Settings, mit denen ein Transcript entstanden ist,
  werden aber nicht mit versioniert."
- „recordings müsste mehr oder weniger immutable sein"
- Zielmodell: `recordings 1:n runs 1:M results`

## Delta zum IST

**IST:**
- `Recording` trägt ALLES: Settings (`enable_vad`, `enable_diarize`,
  `diarize_*`, `enable_streaming`, `enable_noise_reduce`, `enable_enhance`,
  `enable_punctuation`, `enable_llm_enhance`, `llm_endpoint_id`,
  `prompt_template_id`), Betrieb (Status/Progress/Phase/Fehler) und Ergebnis
  (`text`, `segments`, `backend`, `language`).
- `process_recording` (service.py) liest die Settings beim Job-Start aus dem
  `rec`-Objekt (Z. 1387–1396) und schreibt das Ergebnis zurück in `rec`.
- Versions-Historie (`TranscriptVersion`): Snapshot nur bei MUTATIONEN
  (edit ×3, restore, postprocess) — **transcribe/retranscribe erzeugt keine
  Version**, und versioniert werden nur `backend` + `language`, KEINE Settings.
- Reproduzierbarkeit nicht gegeben: „Welche Version entstand mit welchen
  Einstellungen?" ist nicht beantwortbar.

**SOLL (Zielbild, Etappe 1+2):**
- `TranscriptionRun`: 1:n zum Recording — Settings-Snapshot (alle oben),
  Status (queued/processing/done/failed), progress/phase/error, Zeiten,
  Auslöser (`created_by_user_id`), Ergebnis-Zeiger.
- `TranscriptionResult`: 1:M zum Run — `text`, `segments`, Erzeuger, Zeit.
- `Recording` = Stamm: Datei-Metadaten, Eigentümer, Titel, **Zeiger auf den
  aktuellen Run/Result**. Settings/Ergebnis wandern aus dem Recording.
- **Etappe 1 (dieser Change):** Schreibpfad — jeder Transcribe/Re-Transcribe
  erzeugt Run (Settings) + Result (Ergebnis), Recording-Zeiger + Spiegel
  werden aktualisiert (Lesekompatibilität, kein UI-Bruch). Fehlerpfad →
  Run failed. Neuer API-Endpoint listet Runs inkl. Settings.
- **Etappe 2 (Folge-Change):** Lesepfad komplett auf Runs/Results umstellen,
  Recording-Spalten (`enable_*`, `text`, `segments`, …) per Migration
  entfernen (Recording wird physisch schlank/immutable),
  `TranscriptVersion` durch `TranscriptionResult`-Historie ablösen.

## ADDED Requirements

### Requirement: Run-Erzeugung beim Transcribe/Re-Transcribe

- **Ablauf:** `process_recording` legt beim Job-Start (nach dem Settings-Read)
  einen `TranscriptionRun` an: `rec_id`, Settings-Snapshot (die lokalen
  Variablen Z. 1387–1396), `backend`, `language`, `status="processing"`,
  `created_by_user_id=owner_id`. Eigene Session (Worker-Thread).
- **Ergebnis:** `TranscriptionResult` mit `text`/`segments` wird beim
  Abschluss an den Run gehängt (`run_id`), Run auf `done` + `finished_at` +
  ggf. `duration_s`/`language` aktualisiert; `Recording.current_run_id` und
  `Recording.current_result_id` zeigen auf die neuesten Einträge.
- **Fehlerpfad:** Job-Fehler und Abbruch (`_abort_recording`) setzen den
  AKTIVEN Run auf `failed` + `error`-Text. Kein Run ohne Status-Done/Failed.

#### Scenario: Erste Transkription
- **Akteure:** Eingeloggter User, Worker.
- **Eingaben:** Upload + Transkription mit VAD+Diaria an.
- **Ergebnis:** Run (Settings: vad=true, diarize=true, …) + Result (Segmente)
  existieren; die Runs-Liste der Aufnahme zeigt einen Eintrag mit allen
  Settings; Recording-Spiegel unverändert lesbar.

#### Scenario: Re-Transcribe mit anderen Settings
- **Akteure:** User ändert Settings (z. B. Enhance off) und transkribiert neu.
- **Eingaben:** Re-Transcribe.
- **Ergebnis:** NEUER Run mit den neuen Settings + neues Result; der alte
  Run/Result bleibt erhalten (Historie). Anzeige zeigt das neue Ergebnis.

#### Scenario: Fehlschlag
- **Akteure:** Worker, Netzfehler.
- **Eingaben:** Transkription bricht ab.
- **Ergebnis:** Aktiver Run = `failed` mit Fehlertext; kein Result angehängt.

### Requirement: API — Runs auflisten

- **Ablauf:** `GET /api/recordings/{rid}/runs` liefert die Runs der Aufnahme
  (neueste zuerst) mit Settings-Snapshot, Status, Zeiten und
  `result_id`/Segment-Anzahl; eingeloggte Owner/Admin only (User-Isolation
  wie bestehende Endpoints). Run-Detail mit vollem Result über
  `GET /api/recordings/{rid}/runs/{run_id}`.
- **GUI:** (Etappe 2) Versionsliste zeigt Runs/Settings — UI unverändert in
  Etappe 1.

### Requirement: Recording-Spiegel & Deprecation

- **Ablauf:** In Etappe 1 bleiben `Recording.*`-Felder als Read-Mirror
  (API/UI lesen weiterhin `rec.*`); jeder Schreibpfad (Transcribe,
  Post-Process, Edit, Restore) aktualisiert Spiegel + Zeiger konsistent in
  einer Transaktion. Kommentar `Deprecation (Change 094, Etappe 2)` an den
  Spalten.
- **Architektur:** `app/models.py` (TranscriptionRun, TranscriptionResult,
  Zeiger-Spalten), `app/service.py` (Run/Result-Lebenszyklus im Job),
  `app/routers/recordings.py` (API-Endpoint), `app/versions.py` unverändert
  (Etappe 1 parallel).
