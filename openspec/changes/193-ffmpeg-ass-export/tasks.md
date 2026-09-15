# Change 193 — Tasks

## Phase 1: ASS-Generator + Presets (Kern)

- [ ] `app/export/` Verzeichnis anlegen
- [ ] `app/export/presets.py` — Preset-Manager (lädt .ass.j2-Templates, merged Parameter)
- [ ] `app/export/template_engine.py` — Jinja2-basierte Template-Engine (Platzhalter, Schleifen, Filter)
- [ ] `app/export/ass_generator.py` — Nimmt Caption[] + Template + Parameter → .ass-String
- [ ] 5 Standard-Presets als `.ass.j2` unter `app/export/presets/`:
  - [ ] `classic.ass.j2`
  - [ ] `karaoke.ass.j2`
  - [ ] `highlight.ass.j2`
  - [ ] `kinetic.ass.j2`
  - [ ] `modern.ass.j2`
- [ ] Jedes Preset hat `preset.yaml` mit Default-Parametern + Beschreibung
- [ ] Tests: ASS-Generator erzeugt valides ASS für jedes Preset + Caption-Datensatz

## Phase 2: Export-API (Webapp)

- [ ] `routers/export.py` — 2 Endpoints:
  - [ ] `GET /api/recordings/{id}/export/ass?preset=...&params=...` → `.ass`-Datei
  - [ ] `POST /api/recordings/{id}/export` → Body: `{preset, background_video?, params}`
- [ ] Export-Dialog in der UI (`RecordingCard.tsx` oder `ExportDialog.tsx`):
  - [ ] Export-Button neben Restranscribe/Align
  - [ ] Preset-Auswahl (Dropdown/Grid mit Vorschau)
  - [ ] Parameter-Eingabe (Farbe, Größe, Position — optional)
  - [ ] Button: "ASS herunterladen" oder "Video rendern"
- [ ] Fortschritts-Anzeige beim Rendern (WebSocket oder Polling)
- [ ] Tests: ASS-Export-Endpoint, Render-Endpoint, Template-Verarbeitung

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
- [ ] Render-Client in Webapp: `app/export/render_client.py`
- [ ] Fortschritts-WebSocket vom Render-Container
- [ ] Automatische Bereinigung temp-Dateien (24h TTL)
- [ ] Tests: Render-Integration (mockt Container)

## Phase 5: Abnahme

- [ ] CI-Pipeline: Neue Tests grün
- [ ] ASS-Export mit allen 5 Presets auf Prod verifizieren
- [ ] Template-Erstellung + Installation + Sharing auf Prod testen
- [ ] Render-Container (optional) auf Prod starten und Video-Export verifizieren
- [ ] Admin-Doku: Neuer Abschnitt "Export" + "Optionaler Render-Container"
- [ ] OpenSpec archivieren (nach Merge)