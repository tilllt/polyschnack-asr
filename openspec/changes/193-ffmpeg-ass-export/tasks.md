# Change 193 — Tasks

Stand: 17.09.2026 — Phase 1 + 2 sind implementiert (Tests grün), Phase 3–5 offen.

**Abweichungen von der ursprünglichen Planung (aus technischen Gründen):**

- Das Paket heißt `app/ass_export/`, nicht `app/export/`. Ein Paket `app/export/`
  würde das **bestehende Modul `app/export.py`** (Change 008, Template-Exporte für
  TXT/SRT/VTT) verdecken — Python löst `app.export` dann auf das Paket auf und der
  bestehende Export bricht.
- Preset-Dateien heißen `<name>.yaml` (nicht `preset.yaml`): mehrere Presets liegen
  nebeneinander im selben Verzeichnis; `preset.yaml` wäre fünfmal derselbe Name.
- Eine Fortschritts-Anzeige braucht der **ASS-Export** nicht: die Erzeugung dauert
  Millisekunden und läuft synchron im Request. Fortschritt gehört zur Render-Strecke
  (Phase 4) — für Phase 2 wäre ein Fortschrittsbalken eine Anzeige ohne echten Wert.

## Phase 1: ASS-Generator + Presets (Kern)

- [x] `app/ass_export/` Verzeichnis angelegt (siehe Abweichung oben)
- [x] `app/ass_export/presets.py` — Preset-Manager (lädt `.yaml` + Vorlage, merged Parameter, prüft Werte)
- [x] `app/ass_export/template_engine.py` — Jinja2 (`SandboxedEnvironment`, `StrictUndefined`) mit ASS-Filtern
- [x] `app/ass_export/ass_generator.py` — Wort-Timings + Vorlage + Parameter → `.ass`
- [x] 5 Standard-Presets als `.ass.j2` unter `app/ass_export/presets/`:
  - [x] `classic.ass.j2`
  - [x] `karaoke.ass.j2` (`\kf`-Farbverlauf je Wort, Summe = Event-Dauer)
  - [x] `highlight.ass.j2`
  - [x] `kinetic.ass.j2`
  - [x] `modern.ass.j2`
- [x] Jedes Preset hat ein YAML mit Default-Parametern + Beschreibung (de/en/pt)
- [x] Tests: ASS-Generator erzeugt valides ASS für jedes Preset + Caption-Datensatz
  (`tests/test_ass_export.py`, 55 Tests: Struktur, Monotonie, Überlappungsfreiheit,
  Karaoke-Sync, Klammer-Ersatz, Parameter-Grenzen, Misch-/Fallback-Timing)
- [x] Zusätzlich: `tests/test_ass_export_render.py` — die erzeugten Dateien werden mit
  **libass gerendert und pixelweise gemessen** (Karaoke füllt sich, Akzent wandert zum
  nächsten Wort, Aufpoppen startet groß, Social Media blendet Wörter nacheinander ein,
  Klammer-Ersatz ist sichtbar). Ein Struktur-Test allein würde die Wirkung nicht belegen.

## Phase 2: Export-API (Webapp)

- [x] `routers/export.py` — Endpoints:
  - [x] `GET /api/recordings/{id}/export/ass?preset=...&params=...` → `.ass`-Datei
    (409 `no_word_timestamps`, 409 `not_transcribed`, 404 `unknown_preset`,
    400 `invalid_params`, 500 `template_error`; Header `X-Polyschnack-Timing/Words/Lines/Warnings`)
  - [x] `GET /api/export/presets` — Katalog + Parameter-Schema + `used_params` je Preset
  - [x] `POST /api/recordings/{id}/export` → validiert Preset/Parameter und antwortet ohne
    Render-Dienst **503 `render_unavailable`** (Phase 4 schaltet das frei)
- [x] Export-Dialog in der UI (`ExportDialog.tsx`, eingehängt in `RecordingCard.tsx`):
  - [x] Einstieg im bestehenden Download-Dropdown (Konsistenz mit TXT/SRT/VTT/AUD/ZIP,
        statt eines weiteren Buttons in der Knopfreihe)
  - [x] Preset-Auswahl als Kacheln mit Beschreibung in der UI-Sprache
  - [x] Parameter-Eingabe generisch aus dem Backend-Schema (Regler für Zahlen,
        Farbwähler, Schalter, Auswahl) — **nur** die Parameter, die die Vorlage
        benutzt (`used_params`); Rest unter „Weitere Optionen"
  - [x] „ASS herunterladen" (Download per `fetch` + Blob, damit Fehler und
        Warnungen sichtbar sind) — kein Render-Knopf, solange
        `render_available: false`
- [x] Fortschritts-Anzeige: für den ASS-Export nicht nötig (siehe Abweichung oben);
  gehört zu Phase 4
- [x] Tests: `tests/test_export_ass_api.py` (12 Tests) + `ExportDialog.test.tsx` (12 Tests)

## Phase 3: User-Templates (CRUD + Marktplatz)

- [ ] DB-Migration: `templates`-Tabelle + `template_installations`
- [ ] `routers/templates.py`:
  - [ ] `GET /api/templates` — Liste öffentlicher + eigener Templates
  - [ ] `POST /api/templates` — Template erstellen (ASS-J2 + Parameter + Tags)
  - [ ] `PUT /api/templates/{id}` — Bearbeiten
  - [ ] `DELETE /api/templates/{id}` — Löschen (nur Ersteller)
  - [ ] `POST /api/templates/{id}/install` — Installieren (Credits-Prüfung)
  - [ ] `GET /api/templates/{id}/preview` — Vorschau-Generierung
- [ ] GUI: Template-Editor (ASS-Code + Parameter-Eingabe, Syntax-Highlighting)
- [ ] GUI: Template-Marktplatz-Tab (öffentliche Templates, Suchen/Installieren)
- [ ] Template-Versionierung: Update-Hinweis, kein Auto-Update
- [ ] Credit-Transfer-Logik: 90/10-Split Ersteller/Plattform
- [ ] Tests: CRUD, Installation mit/ohne Credits, Transfer-Berechnung

## Phase 4: Optionaler Render-Container (ps-render)

- [ ] Dockerfile für ps-render (Python + ffmpeg + libass)
- [ ] `compose.yml`: Neuer Service `ps-render` mit Profil `render`
- [ ] Render-API: `POST /render` (empfängt .ass + background.mp4, gibt MP4)
- [ ] Render-Client in Webapp: `app/ass_export/render_client.py`
- [ ] Fortschritts-WebSocket vom Render-Container
- [ ] Automatische Bereinigung temp-Dateien (24h TTL)
- [ ] Tests: Render-Integration (mockt Container)

## Phase 5: Abnahme

- [x] CI-Pipeline: Neue Tests grün — Pipeline **5317** (`8dad641`): `test-webapp`,
  `test-frontend`, `grep-gate`, `build-webapp` = success (die `mirror-*`-Jobs
  hängen an `needs:` und laufen länger; Freigabe war `build-webapp`, s. Skill).
- [x] ASS-Export mit allen 5 Presets auf Prod verifizieren — **17.09.2026**,
  `whisper.cia-spandau.de`, Image-Revision `8dad6417` (Label im Container geprüft):
  - `/api/export/presets` → 200, fünf Presets, `render_available: false`;
    `classic` liefert 18 `used_params` **ohne** `accent_color`, `highlight` **mit** —
    die Regel „nur wirkende Regler" greift also live.
  - `GET /api/recordings/<unbekannt>/export/ass` → 404 (Route + Zugriffsprüfung live).
  - Echtes Recording über den Share-Link (414 Wörter, `timing=real`), alle fünf
    Presets geladen: `classic` 76 / `karaoke` 92 / `highlight`, `kinetic`, `modern`
    je 414 Events; `Content-Disposition` + `X-Polyschnack-*`-Header vorhanden.
  - Jede der fünf Dateien mit **libass gerendert**: rc=0, keine libass-Fehler,
    Captions in 27/30 Frames sichtbar; in der Datei 0 ungültige Events und
    0 Überlappungen.
  - Ausgeliefertes Frontend-Bundle (`assets/index-BnERVeki.js`) enthält
    `/api/export/presets`, `/export/ass` und `ass_export_download` — der Dialog
    ist im Prod-Build, nicht nur im Repo.
- [ ] Template-Erstellung + Installation + Sharing auf Prod testen (Phase 3)
- [ ] Render-Container (optional) auf Prod starten und Video-Export verifizieren (Phase 4)
- [ ] Admin-Doku: Neuer Abschnitt "Export" + "Optionaler Render-Container"
- [ ] OpenSpec archivieren (nach Abschluss von Phase 3/4)

### Offen aus der Abnahme

- **Download-Weg korrigiert (17.09., nach der Abnahme):** Der Dialog speicherte die
  Datei über einen `blob:`-Anker. Der Server lieferte 200, beim Nutzer kam aber
  keine Datei an (belegt im Traefik-Zugriffsprotokoll: `200 GET …/export/ass?preset=
  highlight&params=…` um 19:10:31 bzw. `kinetic` 19:11:22, keine gespeicherte Datei).
  Jetzt derselbe Weg wie bei TXT/SRT/AUD: `downloadUrl(url, name)` setzt einen
  Anker auf die **API-URL** (Server schickt `Content-Disposition: attachment`),
  der `fetch` bleibt nur zur Prüfung/Meldung. Zusätzlich steht unter dem Dialog ein
  sichtbarer Ersatzlink („Nichts gespeichert? Hier klicken").
  Nachgewiesen: gegen einen echten HTTP-Server im Chromium gespeichert (128 B,
  korrekter Inhalt), auch bei sofortigem Entfernen des Ankers; im vollen
  GUI-Durchlauf feuert das Download-Ereignis mit der API-URL als Ziel.
  Tests: 461 Frontend-Tests grün, `tsc + vite` grün.

- **Share-Link-Recordings haben teils kryptische Titel** (`iy7szEP8szHBeVVpmKSSVX.ass`
  als Dateiname, weil `original_name` beim URL-Import so heißt). Der Export nutzt
  korrekt den Titel/das Original — die Datei heißt dann eben so. Bei Bedarf den
  Dateinamen im Dialog editierbar machen (nicht Teil dieses Changes).
- Der **anonyme** Export über einen aktiven Share-Link funktioniert (read-Recht).
  Für eingeloggte Nutzer ist der Weg identisch; ein Wire-Test mit Session ist
  ohne echtes Konto nicht möglich (OIDC=1) — die 404-Probe belegt Route + Guard.

