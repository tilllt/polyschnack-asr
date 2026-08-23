## ADDED Requirements

### Requirement: Run-Erzeugung beim Transcribe/Re-Transcribe

- **Ablauf:** `process_recording` legt beim Job-Start einen
  `TranscriptionRun` an: `rec_id`, Settings-Snapshot (`backend`, `language`,
  `enable_vad`, `enable_diarize`, `diarize_num_speakers`,
  `diarize_min_duration_off`, `diarize_method`, `enable_streaming`,
  `enable_noise_reduce`, `enable_enhance`, `enable_punctuation`,
  `enable_llm_enhance`, `llm_endpoint_id`, `prompt_template_id`),
  `status="processing"`, `started_at`, `created_by_user_id`. Beim Abschluss
  hängt ein `TranscriptionResult` (text + segments) am Run; der Run wird auf
  `done` (+ duration_s/language/finished_at) gesetzt, und
  `Recording.current_run_id`/`current_result_id` zeigen auf die neuen
  Einträge. Job-Fehler und Abbruch markieren den aktiven Run als `failed`
  mit Fehlertext.
- **Versionierung:** Die Settings eines Laufs sind damit versioniert —
  „welche Version entstand mit welchen Einstellungen?" ist beantwortbar.
  Jeder Re-Transcribe erzeugt einen NEUEN Run; die Historie bleibt erhalten.
- **Architektur:** `app/models.py` (TranscriptionRun, TranscriptionResult,
  Recording-Zeiger), `app/service.py` (Run/Result-Lebenszyklus im Job).

#### Scenario: Erste Transkription

- **Akteure:** Eingeloggter User, Worker.
- **Eingaben:** Upload + Transkription mit VAD + Diarisierung.
- **Ergebnis:** Run (Settings-Snapshot vad=true, diarize=true, …) + Result
  (Segmente) existieren; die Runs-Liste der Aufnahme zeigt einen Eintrag mit
  allen Settings; Recording-Spiegel bleibt lesbar (Anzeige = Export).

#### Scenario: Re-Transcribe mit anderen Settings

- **Akteure:** User ändert Settings (z. B. Enhance off) und transkribiert neu.
- **Eingaben:** Re-Transcribe.
- **Ergebnis:** NEUER Run mit den neuen Settings + neues Result; der alte
  Run/Result bleibt erhalten. Anzeige zeigt das neue Ergebnis.

#### Scenario: Fehlschlag

- **Akteure:** Worker, Netzfehler.
- **Eingaben:** Transkription bricht ab.
- **Ergebnis:** Aktiver Run = `failed` mit Fehlertext; kein Result angehängt.

### Requirement: API — Runs auflisten

- **Ablauf:** `GET /api/recordings/{rid}/runs` liefert die Runs einer
  Aufnahme (neueste zuerst) mit Settings-Snapshot, Status, Zeiten,
  `result_id` und `segment_count`; `GET /api/recordings/{rid}/runs/{run_id}`
  liefert den Run mit vollem Ergebnis (Text + Segmente). Owner/Admin only
  (User-Isolation wie bestehende Endpoints).
- **Architektur:** `app/routers/recordings.py` (zwei neue Endpoints).

#### Scenario: Runs-Liste abrufen

- **Akteure:** Owner.
- **Eingaben:** GET /api/recordings/r1/runs.
- **Ergebnis:** Liste mit allen Läufen, neuester zuerst, Settings + Status +
  Segment-Anzahl je Run.

#### Scenario: Fremder User

- **Akteure:** Nicht-Owner.
- **Eingaben:** GET /api/recordings/r1/runs.
- **Ergebnis:** 401/403 (kein Datenleck über User-Grenzen).

### Requirement: Recording-Spiegel & Deprecation

- **Ablauf:** Die Settings-/Ergebnis-Spalten am `Recording` bleiben in
  Etappe 1 als Read-Mirror (API/UI unverändert); jeder Schreibpfad
  aktualisiert Spiegel + Zeiger konsistent. Die Spalten sind als
  Deprecation markiert; Etappe 2 (Folge-Change) stellt den Lesepfad auf
  Runs/Results um und entfernt die Spalten per Migration.
- **Architektur:** `app/models.py` (Deprecation-Kommentar, Zeiger).

#### Scenario: Bestehende UI

- **Akteure:** User mit alter UI.
- **Eingaben:** Aufnahme öffnen.
- **Ergebnis:** Unverändertes Verhalten (Recording-Spiegel liefert Settings/
  Ergebnis); parallel wächst die Run-Historie mit.
