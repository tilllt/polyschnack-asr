# Change Proposal 014 — User-Speicher-Isolation + Self-Healing für kaputte Recordings + editierbarer Titel

**Status:** Proposed

## Why

Drei User-Befunde (2026-08-18):

1. **Datei-Ablage ist ein einziger flacher Ordner.** Alle Audio-Dateien liegen
   als `{uuid}.{ext}` direkt in `AUDIO_DIR`; die Zuordnung zu einem User
   existiert nur in der DB (`Recording.user_id`). Sicherheitstechnisch ist das
   suboptimal: Retention, Quota und Backup müssen pro User über die DB
   gefiltert werden statt über die Platte, und ein DB-Fehler (falsche
   `stored_path`-Referenz) kann Dateien eines anderen Users treffen. Frage des
   Users: „Würde es aus Sicherheitsgründen Sinn machen, wenn die Files der
   User in userspezifischen Ordnern liegen?" — **Ja.** User-Ordner unter
   `AUDIO_DIR/<user_id>/` schaffen eine zweite, unabhängige Zugriffsgrenze
   (Platte + DB), machen Retention/Quota/Backup pro User trivial und
   verhindern, dass ein `stored_path`-Tippfehler auf fremde Dateien zeigt.

2. **Orphan-Einträge in der GUI sind weder abspiel- noch löschbar.** Es gibt
   Aufnahmen, deren Audio-Datei fehlt oder beschädigt/falsches Format ist
   (z.B. 78-Byte-WAV). Die GUI zeigt sie, aber Playback und
   Re-Transcribe scheitern. **Root Cause:** `permissions.py` vergibt für
   `rec.user_id is None` (Legacy-public) NUR `read` — der DELETE-Endpoint
   (`delete_recording_endpoint`) verlangt `full` → **403**. Diese Einträge
   sind damit für JEDEN unantastbar. Das bestehende Self-Healing
   (`orphan_sweep.py`) räumt nur Dateien OHNE DB-Eintrag ab — die
   Gegenrichtung (DB-Eintrag OHNE gültige Datei) fehlt komplett.

3. **Titel ist an den Dateinamen gekoppelt.** Der Anzeige-Titel ist hart
   `rec.original_name`; es gibt keinen eigenen Titel. Der User will: Titel
   default = Dateiname, aber editierbar; die Dateinamen-Verknüpfung muss
   anders gespeichert werden (Sidecar-JSON neben der Audio-Datei), damit
   Titel und Datei unabhängig bleiben; wenn der Dateiname (Titel) geändert
   wird, soll darunter in einer zweiten, kleineren Zeile der ursprüngliche
   Dateiname angezeigt werden.

## What

Drei Verhaltensänderungen:

1. **User-Ordner:** Neue Uploads (und davon abgeleitete Dateien: Crop,
   Re-Transcribe-WAV, URL-Import) liegen unter
   `AUDIO_DIR/<user_id>/<uuid>.<ext>` (eingeloggte User) bzw.
   `AUDIO_DIR/anon/<uuid>.<ext>` (anonyme User, `user_id` ist immer gesetzt —
   anon-Session). Legacy-Dateien im flachen `AUDIO_DIR` bleiben lesbar
   (Orphan-Sweep und Playback ignorieren den Pfad nicht), werden aber bei
   Gelegenheit (Re-Transcribe) in den User-Ordner verschoben. Bestehende
   `stored_path`-Werte bleiben gültig.

2. **Self-Healing für kaputte Recordings:**
   - **Delete/Re-Transcribe auch für `user_id=None`-Recordings möglich.**
     Der Owner (eingeloggter User ODER der anon-User der Session, falls die
     Recording von dieser Session erzeugt wurde) bekommt `full`. Dafür wird
     die Owner-Zuordnung für Legacy-Einträge nachgezogen: eine Spalte
     `owner_user_id` (nullable) auf `Recording` — beim ersten Zugriff oder
     via Migrations-Job wird sie aus dem Upload-Kontext gesetzt, wo
     verfügbar; Restore (`recovery.py`) setzt sie explizit.
   - **Self-Healing-Scan:** Ein neuer Job (Startup + täglich, wie
     `stale_jobs.py`) prüft pro Recording, ob `stored_path` existiert UND
     ein gültiges Audio-Format hat (Magic-Bytes + Mindestgröße). Fehlt die
     Datei oder ist sie ungültig → Status `failed` mit
     `error="Audio-Datei fehlt oder ist beschädigt"` + GUI zeigt einen
     „Defekt"-Badge und macht Delete prominent. Die GUI-Fehler „stiller
     Fehler" sind damit sichtbar.
   - **Prävention:** `prepare_storage` validiert bereits das Format beim
     Upload; zusätzlich wird beim Upload die Datei NACH dem Write per
     `probe_duration_path` verifiziert — existiert die Datei nach dem Commit
     nicht mehr (Crash-Fenster), markiert der Scan sie als `failed`
     (statt still zu verschwinden).
   - **Playback-404 wird sichtbar:** Der Audio-Endpoint liefert bei fehlender
     Datei einen sauberen 410/404 mit klarer Message, die GUI zeigt den
     Defekt-Badge statt stiller Fehlerspirale.

3. **Editierbarer Titel:**
   - Neues Feld `title` (nullable) auf `Recording`; API-Serialisierung liefert
     `title` (Fallback: `original_name`).
   - **Sidecar-JSON** `{stored_path}.meta.json` neben der Audio-Datei speichert
     `{"title": ..., "original_name": ...}` — die Dateinamen-Verknüpfung ist
     damit unabhängig von der DB (überlebt DB-Resets/Exports, wandert mit
     der Datei). DB-Feld bleibt Quelle der Wahrheit; Sidecar wird bei
     Änderungen mitgeschrieben und beim Re-Transcribe/Export ausgelesen.
   - PATCH `POST /api/recordings/{rid}/title` (oder PATCH `/recordings/{rid}`)
     setzt den Titel, schreibt Sidecar + DB.
   - GUI: Titel editierbar (Stift-Icon / Inline-Edit); darunter in zweiter,
     kleinerer Zeile der ursprüngliche Dateiname (`original_name`), wenn er
     sich vom Titel unterscheidet.

## Changes

- `Recording`-Model: + `title: Optional[str]`, + `owner_user_id: Optional[int]`
  (Migration via `ALTER TABLE`-Helper, vorhandenes Muster aus Change 009).
- `permissions.py`: Owner-Logik für `user_id=None` → `owner_user_id`-Fallback;
  anon-Session-Owner erkennt eigene Einträge.
- `routers/recordings.py`: Upload/Crop/URL-Import schreiben in User-Ordner;
  DELETE erlaubt Owner auch bei `user_id=None`; PATCH-Titel-Endpoint;
  Audio-Endpoint 404 → klare Fehlermeldung.
- `orphan_sweep.py` + neuer `recording_health.py`: Scan prüft DB↔Datei in
  beide Richtungen; kaputte Recordings → `failed` + Badge.
- `audio_utils.py`: `prepare_storage` + Sidecar-Helfer (read/write
  `{path}.meta.json`).
- Frontend: Titel-Inline-Edit + Dateiname als zweite Zeile; Defekt-Badge;
  Delete-Button auch bei defekten Einträgen.

## Downgrade

- User-Ordner: `stored_path`-Werte sind bereits in der DB — Downgrade = nur
  neue Uploads wieder flach ablegen (Config-Flag), bestehende bleiben.
- Self-Healing-Scan: Job deaktivieren (Config-Flag) — Einträge bleiben
  `failed`, kein automatischer Eingriff.
- Titel: Spalten + Sidecar bleiben harmlos; PATCH-Endpoint entfernen.

## Specs-Delta

- ADDED: `specs/storage-security/spec.md` (User-Ordner, Sidecar, Self-Healing)
- MODIFIED: `specs/recordings/spec.md` (Titel, Delete-Ownership, Defekt-Badge)
