## ADDED Requirements

### Requirement: User-Ordner für Audio-Dateien

- **Ablauf:** Neue Uploads und davon abgeleitete Dateien (Crop-WAV,
  Re-Transcribe-Ergebnis, URL-Import) werden unter
  `AUDIO_DIR/<user_id>/<uuid>.<ext>` abgelegt (eingeloggte User) bzw.
  `AUDIO_DIR/anon/<uuid>.<ext>` (anonyme Sessions). Die Zuordnung erfolgt
  über die aktuell authentifizierte Identität (`_current_user`).
- **Legacy-Kompatibilität:** Bestehende Dateien im flachen `AUDIO_DIR`
  bleiben gültig — Playback, Download, Orphan-Scan und Re-Transcribe
  arbeiten weiter mit dem gespeicherten `stored_path`. Ein Re-Transcribe
  einer Legacy-Aufnahme schreibt das Ergebnis in den User-Ordner des
  aktuellen Users (und aktualisiert `stored_path`).
- **Isolation:** Ein `stored_path`-Tippfehler oder DB-Korruptionsfall kann
  nie auf die Datei eines anderen Users zeigen — der Zielordner wird aus
  der User-ID des aktuellen Requests gebildet, nie aus dem Dateinamen.
- **Architektur:** `app/routers/recordings.py` (Upload, Crop,
  Re-Transcribe), `app/routers/url_import.py`, `app/config.py`
  (`AUDIO_DIR` bleibt Basis), neue Helfer in `app/audio_utils.py`
  (`storage_path_for(user_id, ext)`).

#### Scenario: Upload eines eingeloggten Users

- **Akteure:** Eingeloggter User mit OIDC-Session.
- **Eingaben:** WAV-Datei hochladen.
- **Ergebnis:** Datei liegt unter `AUDIO_DIR/<user_id>/<uuid>.wav`;
  `Recording.stored_path` zeigt dorthin; Playback und Download funktionieren.

#### Scenario: Upload einer anonymen Session

- **Akteure:** Anonymer Besucher (Cookie-Session).
- **Eingaben:** MP3 hochladen.
- **Ergebnis:** Datei liegt unter `AUDIO_DIR/anon/<uuid>.mp3`; die
  anon-Session ist Owner (full access); Retention löscht Eintrag + Datei
  gemeinsam.

### Requirement: Self-Healing für Recordings ohne gültige Datei

- **Ablauf:** Ein regelmäßiger Job (Startup + täglich, neben `stale_jobs.py`)
  prüft jede Recording: `stored_path` existiert UND hat gültige Audio-Magic
  (RIFF/WAVE, ftyp/mp4, ID3, OggS) UND Mindestgröße (> 256 Byte). Verletzt
  eine Recording das → `status="failed"`, `error="Audio-Datei fehlt oder ist
  beschädigt"`, `progress_pct` unverändert.
- **Delete-Fix:** Der DELETE-Endpoint verlangt `full`; Legacy-public
  Recordings (`user_id is None`) vergaben bisher nur `read` → 403. Neu:
  `owner_user_id`-Spalte auf `Recording`; Owner = `rec.user_id` oder
  `rec.owner_user_id`; bei `user_id is None` UND `owner_user_id is None`
  darf ein Admin (oder der anon-User, wenn `owner_user_id` von dessen
  Session gesetzt wurde) löschen. Re-Transcribe analog.
- **Sichtbarkeit:** Der Audio-Endpoint liefert bei fehlender Datei
  `404` + klare Message („Audio-Datei nicht gefunden"); die GUI zeigt für
  `status="failed"` mit diesem Fehler einen Defekt-Badge und aktiviert
  Delete auch bei defekten Einträgen (kein stiller Fehler).
- **Prävention:** Upload validiert bereits Format (`prepare_storage`);
  zusätzlich wird die frisch geschriebene Datei per `probe_duration_path`
  verifiziert (bestehendes Muster). Die Lücke „Datei nach DB-Commit
  verloren" deckt der Scan ab.
- **Architektur:** neue `app/recording_health.py` (Scan + Fix),
  `app/routers/recordings.py` (DELETE/Re-Transcribe-Ownership,
  Audio-404-Message), `app/permissions.py` (Owner-Logik), `app/main.py`
  (Startup-Registrierung).

#### Scenario: Recording mit verlorener Datei wird markiert

- **Akteure:** System (Self-Healing-Job), Besitzer.
- **Eingaben:** Datei unter `stored_path` wird entfernt; Job läuft.
- **Ergebnis:** Recording zeigt `status="failed"` mit klarem Fehlertext;
  der Besitzer sieht den Defekt-Badge und kann sie löschen (DELETE ok).

#### Scenario: Legacy-public-Recording löschen

- **Akteure:** Admin oder anon-Owner (per `owner_user_id`).
- **Eingaben:** DELETE auf eine Recording mit `user_id=None`.
- **Ergebnis:** Löschung gelingt (kein 403); Datei + Sidecar + abhängige
  Zeilen (Versions, Shares) werden entfernt.

### Requirement: Editierbarer Titel + Sidecar-Metadaten

- **Ablauf:** `Recording` bekommt `title: Optional[str]` (Default:
  `original_name` beim Upload). Die API-Serialisierung liefert `title`
  (Fallback `original_name`). Ein PATCH-Endpoint
  `PATCH /api/recordings/{rid}` (oder `POST /title`) setzt den Titel —
  Owner/Admin only.
- **Sidecar-JSON:** Neben der Audio-Datei liegt `{stored_path}.meta.json`
  mit `{"title": ..., "original_name": ...}`. DB ist Quelle der Wahrheit;
  das Sidecar wird bei Titel-Änderungen mitgeschrieben und beim
  Re-Transcribe/Export gelesen — die Dateinamen-Verknüpfung überlebt damit
  DB-Resets und wandert mit der Datei.
- **GUI:** Der Titel ist editierbar (Stift/Inline-Edit). Unterscheidet sich
  der ursprüngliche Dateiname (`original_name`) vom Titel, erscheint er in
  einer zweiten, kleineren Zeile unter dem Titel. Bei Export/Download wird
  der Dateiname weiterhin aus `original_name` gebildet (unverändert).
- **Architektur:** `app/models.py` (title, owner_user_id),
  `app/routers/recordings.py` (PATCH-Titel, Serialisierung),
  `app/audio_utils.py` (Sidecar-Helfer read/write), `RecordingCard.tsx`
  (Titel-Edit + zweite Zeile), `api.ts` (Typ + PATCH-Call).

#### Scenario: Titel ändern

- **Akteure:** Besitzer.
- **Eingaben:** Stift-Icon am Titel → „Besprechung KW34" eintippen → Enter.
- **Ergebnis:** Karten-Kopf zeigt „Besprechung KW34", darunter klein den
  ursprünglichen Dateinamen; Sidecar + DB aktualisiert; Download nutzt
  weiterhin den Dateinamen.
