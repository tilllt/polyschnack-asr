# Transcription

## Purpose

Aufnahmen hochladen, mit einem ASR-Backend transkribieren (auch erneut),
optional per Toggles anreichern, als Versionen sichern und in gängigen
Formaten exportieren.

## Requirements

### Req 1: Upload

- **Ablauf:** `POST /api/recordings` (Multipart: file, batch_id, Toggle-Flags).
  Duplikat-Erkennung per SHA-256-Content-Hash → 409 mit `existing_id`
  (oder `force=true` erzwingt neuen Eintrag). Anon-Limits werden geprüft.
- **Eingaben:** Audio-Datei (mp3/wav/ogg/m4a…), optional `force`.
- **Ausgaben:** Recording-Objekt; bei Duplikat `{duplicate: true, existing_id}`.
- **Ergebnis:** Datei liegt in `DATA_DIR`, DB-Zeile mit `status="uploaded"`.
- **Architektur:** `routers/recordings.py`, `crud.py`; Audio-Pfad
  `DATA_DIR/audio/…`, `stored_path` in der DB.

#### Scenario: Doppelter Upload

- **Akteure:** Registrierter User.
- **Eingaben:** Dieselbe Datei zweimal hochladen.
- **Ausgaben:** 409 mit `existing_id`; zweiter Eintrag mit `force=true` möglich.

### Req 2: Transkribieren & Retranskribieren

- **Ablauf:** `POST /api/recordings/{id}/transcribe` (Form) bzw.
  `POST /api/recordings/{id}/retranscribe` (JSON). Backend wählbar
  (Default: `POLYSCHNACK_DEFAULT_BACKEND` bzw. `DATA_DIR/config.json`).
  Job geht in die Queue; Worker ruft `get_client(backend).transcribe_async`.
- **Eingaben:** Toggles (VAD, Diarize, Streaming, Noise-Reduce, Enhance),
  Backend, Post-Processing-Auswahl (Template, Target, BYOK-Endpunkt).
- **Diarization-Tuning:** Zusätzlich `diarize_num_speakers` (int, optional)
  und `diarize_min_duration_off` (float, optional) bei transcribe/retranscribe/
  upload/from-url. Werden am Recording gespeichert und bei Re-Transcribe
  wieder verwendet; `None` → pyannote-Pipeline-Default. `service.py` reicht
  beide an `diarize.py::diarize(num_speakers=…, min_duration_off=…)`, das
  sie als `min_speakers/max_speakers` bzw. `min_duration_off` an die
  Pipeline übergibt. Das UI bietet „Sprecherzahl" (Auto/1/2/3/4+) und
  „Sensitivität" (Weniger Wechsel 0.4 s / Standard / Mehr Detail 0.05 s)
  in einem ausklappbaren Menü an der Transcribe-Zeile.
- **Ausgaben:** `{status, position}` — Position in der Backend-Queue.
- **Ergebnis:** `status` durchläuft `queued → processing → done|failed`;
  Fortschritt via WebSocket/`progress_pct`; Ergebnis (text, segments,
  language, duration) in der DB.
- **Architektur:** `service.py::process_recording` (Worker), `queue.py`,
  `routers/recordings.py`; ASR-Client-Interface mit `transcribe_async`.

#### Scenario: Re-Transkription mit anderem Backend

- **Akteure:** Besitzer oder Share mit `write`/`full`.
- **Eingaben:** `retranscribe` mit `backend="crispr-qwen3"`.
- **Ergebnis:** Neue Version `kind="retranscribe"`; alte Fassung bleibt
  per Diff/Restore erreichbar.

#### Scenario: Bekannte Sprecherzahl vorgeben

- **Akteure:** Besitzer oder Share mit `write`/`full`.
- **Eingaben:** Re-Transkription mit `diarize_num_speakers=2` bei einer
  2-Sprecher-Aufnahme.
- **Ergebnis:** Diarization liefert genau 2 Sprecher (min=max=2) statt
  frei geschätzter 3; Segmente tragen nur SPEAKER_00/SPEAKER_01.

#### Scenario: Weniger Sprecherwechsel

- **Akteure:** Besitzer.
- **Eingaben:** Re-Transkription mit `diarize_min_duration_off=0.4`.
- **Ergebnis:** Kurze Pausen (<0.4 s) lösen keinen Sprecherwechsel aus —
  weniger Label-Flickering bei schnellen Dialogwechseln.

### Req 3: Opt-in-Toggles (Punctuation, LLM-Enhance)

- **Ablauf:** Pro Aufnahme setzbar (Form/JSON). Nichts läuft automatisch —
  Defaults (`POLYSCHNACK_DEFAULT_PUNCTUATION`, `POLYSCHNACK_DEFAULT_LLM_ENHANCE`)
  sind aus. Punctuation-Modus: `POLYSCHNACK_PUNCTUATION_MODE`
  (`off|local|llm`); `llm` und LLM-Enhance sind **paid** → nur registrierte User.
- **Ergebnis:** Text/Segmente werden nach der Erkennung nachbearbeitet;
  LLM-Ergebnisse als neue Version `kind="postprocess"`.

#### Scenario: LLM-Optimierung nur für registrierte User

- **Akteure:** Anonymer User.
- **Eingaben:** `enable_llm_enhance=true`.
- **Ergebnis:** 403 (paid-Pfad); UI zeigt den Schalter ausgegraut.

### Req 4: Versionen & Diff/Restore

- **Ablauf:** Bei jeder Änderung (transcribe, retranscribe, edit, restore,
  postprocess) wird ein Voll-Snapshot (`TranscriptVersion`) angelegt.
  `GET /api/recordings/{id}/versions`, `GET …/versions/{v}/diff`,
  `POST …/versions/{v}/restore`.
- **Ausgaben:** Versionen mit `version_no`, `kind`, `created_at`; Diff als
  Text-Diff; Restore setzt text/segments zurück (erzeugt `kind="restore"`).
- **Architektur:** `routers/versions.py`, `versions.py` (snapshot/list/diff).

#### Scenario: Falsche Änderung zurückrollen

- **Akteure:** Besitzer.
- **Eingaben:** Restore auf Version 2 nach fehlerhaftem Edit.
- **Ergebnis:** text/segments von Version 2; neue Version `kind="restore"`.

### Req 5: Segment-Editing

- **Ablauf:** `PATCH /api/recordings/{id}/segments/{idx}` — ändert ein Segment
  und den Gesamttext; erzeugt Version `kind="edit"`.
- **Wichtig (JSON-Mutation):** SQLAlchemy erkennt In-Place-Mutationen von
  JSON-Spalten nicht → tiefe Kopie (`json.loads(json.dumps(...))`) vor dem
  Schreiben.

#### Scenario: Wort korrigieren

- **Akteure:** Besitzer (oder Share `write`).
- **Eingaben:** PATCH Segment 3 auf „Hallo Welt".
- **Ergebnis:** Segment + Gesamttext aktualisiert; Edit-Version gesichert.

### Req 6: Export

- **Ablauf:** `GET /api/recordings/{id}/export?format=txt|srt|vtt|json`.
- **Ausgaben:** Download-Datei (JSON: text+segments+versions).
- **Architektur:** `export.py`.

#### Scenario: Untertitel exportieren

- **Akteure:** Beliebig mit Zugriff.
- **Eingaben:** `export?format=srt`.
- **Ausgaben:** SRT-Datei mit Segment-Timestamps.
