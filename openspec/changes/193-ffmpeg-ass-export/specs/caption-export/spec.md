# Caption Export

## ADDED Requirements

### Requirement: ASS-Export pro Recording

- **Ablauf:** Registrierte User laden die Untertitel eines Recordings als
  `.ass`-Datei herunter (`GET /api/recordings/{id}/export/ass`) oder stoßen
  ein gebranntes Video an (`POST /api/recordings/{id}/export`).
- **Eingaben:** Preset-ID (oder User-Template-ID), optionale Parameter
  (Farben, Schriftgröße, Position), optional Background-Video.
- **Ausgaben:** `.ass`-Datei (Download) bzw. Job mit `status` und
  Fortschritt; fertiges MP4 über temporären Download-Link (24 h).
- **Ergebnis:** Das ASS nutzt die Wort-Timestamps des Recordings; ohne gültige
  Wortzeiten antwortet die API mit 409 `{"error": "no_word_timestamps"}`.
- **Architektur:** `routers/export.py`, `export/ass_generator.py`,
  `export/template_engine.py`; ASS-Erzeugung ist rein serverseitig.

#### Scenario: ASS herunterladen

- **Akteure:** Besitzer oder Share mit `read`-Rechten.
- **Eingaben:** `GET /api/recordings/{id}/export/ass?preset=highlight`.
- **Ergebnis:** 200 mit Content-Type `text/plain` (oder `application/x-ass`),
  Datei enthält `[Script Info]`- und `[Events]`-Sektionen mit einem
  `Dialogue`-Event pro sichtbarem Wort-Schritt.

#### Scenario: Export ohne Wortzeiten

- **Akteure:** Besitzer eines Recordings, das nur Segment- (keine Wort-)Zeiten hat.
- **Eingaben:** `GET /api/recordings/{id}/export/ass?preset=classic`.
- **Ergebnis:** 409 mit `{"error": "no_word_timestamps"}` und Hinweis,
  zuerst zu alignen.

### Requirement: Standard-Presets

- **Ablauf:** PolySchnack liefert fertige Presets, die alle Styles der
  modernen Social-Media-Untertitel abdecken.
- **Ausgaben:** Preset-Katalog via `GET /api/export/presets`: `classic`,
  `karaoke`, `highlight`, `kinetic`, `modern` — jeweils mit Name,
  Beschreibung, Default-Parametern und Vorschau.
- **Ergebnis:** Jedes Preset besteht aus einer ASS-Jinja2-Vorlage plus
  Parameter-Schema (Farben, Schriftgröße, Position, Timing).
- **Architektur:** `export/presets/` (`.ass.j2` + `preset.yaml`), geladen
  durch `export/presets.py`.

#### Scenario: Preset-Liste abrufen

- **Akteure:** Angemeldeter User.
- **Eingaben:** `GET /api/export/presets`.
- **Ergebnis:** 200 mit allen 5 Standard-Presets inkl. `parameters`-Schema.

### Requirement: User-Templates

- **Ablauf:** Angemeldete User erstellen eigene ASS-Vorlagen und verwenden
  sie wie Standard-Presets beim Export.
- **Eingaben:** `POST /api/templates` mit `name`, `ass_template`
  (Jinja2 + ASS-Platzhalter), `parameters` (JSON-Schema), `tags`,
  `visibility` (`private`/`public`/`link_only`).
- **Ausgaben:** Template-Objekt mit `id`, `version`, `created_at`.
- **Ergebnis:** Templates sind nach Kategorie und Tag durchsuchbar; der
  Ersteller kann sie bearbeiten, löschen und (bei public/link_only) teilen.
- **Architektur:** `routers/templates.py`; DB-Tabelle `templates`.

#### Scenario: Eigene Vorlage erstellen

- **Akteure:** Angemeldeter User mit aktivem Konto.
- **Eingaben:** `POST /api/templates` mit gültiger ASS-Jinja2-Vorlage und
  Parameter-Schema.
- **Ergebnis:** 201 mit Template-Objekt; Template erscheint im
  Export-Dialog unter „Meine Templates".

#### Scenario: Template aktualisieren

- **Akteure:** Template-Ersteller.
- **Eingaben:** `PUT /api/templates/{id}` mit neuem `ass_template`.
- **Ergebnis:** 200; `version` erhöht sich. Installateure bekommen im
  Export-Dialog einen Update-Hinweis, kein automatisches Überschreiben.

### Requirement: Video-Rendering über optionalen Container

- **Ablauf:** Für MP4-Export wird ein separater Render-Dienst aufgerufen;
  ohne ihn steht nur der ASS-Download zur Verfügung.
- **Ausgaben:** `POST /api/recordings/{id}/export` mit
  `mode="render"` liefert ein Job-Objekt; Fortschritt via WebSocket;
  fertiges MP4 per Download-Link.
- **Ergebnis:** Der Kern läuft ohne Render-Container; der Render-Service ist
  ein optionaler Compose-Service (Profil `render`).
- **Architektur:** `export/render_client.py` → Docker-Service `ps-render`
  (ffmpeg + libass).

#### Scenario: Render deaktiviert

- **Akteure:** Besitzer, Installation ohne Render-Container.
- **Eingaben:** `POST /api/recordings/{id}/export` mit `mode="render"`.
- **Ergebnis:** 503 `{"error": "render_unavailable"}` mit Hinweis auf
  ASS-Download.