# Change 193 — FFmpeg + ASS Export: Caption-Video mit Presets + Template-Marktplatz

**Status:** Proposal

## Warum

PolySchnack hat Wort-Timestamps — kann aber keinen Video-Export mit Untertiteln. 
Remotion ist lizenz-technisch unsicher für eine kommerzielle Plattform. FFmpeg + ASS 
(Advanced SubStation Alpha) ist LGPL/GPL, voll kommerziell nutzbar, bereits im Stack 
und mächtig genug für TikTok-Stil-Untertitel.

Gleichzeitig soll die Plattform User einbinden: Eigene Templates erstellen, teilen, 
gegen Credits handeln.

## Was sich ändert (Verhaltens-Delta)

### Neu: Export-Button pro Recording

- Jedes Recording bekommt einen **Export**-Button (Neben Transcribe/Restranscribe/Align/Delete)
- Klick öffnet Export-Dialog: Preset auswählen (Standard oder User-Templates)
- Optionen: **ASS-Datei** herunterladen (leichter Export ohne ffmpeg) oder 
  **Video brennen** (MP4 mit eingebrannten Captions)
- Bei Video-Export: optionales Hintergrund-Video (kann das Recording-Audio/Video sein 
  oder ein Standard-Background)

### Neu: ASS-Presets (PolySchnack-Standard)

| Preset | Effekt |
|--------|--------|
| **Classic** | Weiße Schrift, schwarze Outline, unten zentriert, ein- und ausblendend |
| **Karaoke** | Wort-Farbverlauf von links nach rechts (`\k`-Karaoke) |
| **Highlight** | Aktuelles Wort farbig, Rest ausgegraut (`{\alpha&HFF}`-Transparenz) |
| **Kinetic** | Aktuelles Wort leicht vergrößert und angehoben (`\move` + `\t`-Scale) |
| **Modern** | Moderne Social-Media-Optik: Große Schrift, Zentriert, Wort-für-Wort-Erscheinen |

Jedes Preset = eine `.ass`-Datei + Parameter (Farben, Position, Größe, Timing).

### Neu: User-Templates

- User können eigene ASS-Templates erstellen — entweder **per GUI** (Template-Editor, 
  Farbe/Position/Größe/Karaoke wählbar) oder **als .ass-Datei hochladen**
- Templates haben: Namen, Beschreibung, Tags, Vorschau-Thumbnail, Version
- Private Templates (nur ich) oder Public (für alle sichtbar)
- Template-Engine: User-Template = `.ass`-Vorlage mit Platzhaltern 
  (`{{word}}`, `{{start_ms}}`, `{{end_ms}}`, `{{line}}`, `{{words_per_line}}`, 
  `{{font_size}}`, `{{primary_color}}`, …)

### Neu: Template-Marktplatz

- **Listing:** Öffentliche Templates im Export-Dialog oder einem "Community"-Tab
- **Installa tion:** Ein Klick → Template land in meiner Bibliothek
- **Teilen:** Drei Modi:
  1. **Kostenlos** — jeder kann installieren
  2. **Credits-Tausch** — Download kostet vom Ersteller festgelegte Credits
  3. **Exklusiv** — nur mit direktem Share-Link installierbar (Link-Token)

- **Ersteller-Vergütung:** Bei Credits-Tausch fließen die Credits dem Ersteller zu 
  (abzüglich Plattform-Anteil, z. B. 10 %). Die Credits kommen aus dem User-Guthaben 
  (bestehendes Kredit-System).

### Neu: Optionaler Render-Container

- Das ffmpeg-Video-Rendering läuft in einem **separaten Docker-Container** 
  (`ps-render`), nicht in der Webapp. Die Webapp erzeugt nur die `.ass`-Datei und 
  ruft den Render-Container per API.
- Der Container ist **optional** aktivierbar (Compose-Profil `render`). 
  Ohne ihn: nur ASS-Download (kein gebranntes Video).
- Lizenz-technisch sauber: PolySchnack-Kern bleibt unabhängig von der Render-Engine.

### API-Änderungen

| Methode | Pfad | Änderung |
|---------|------|----------|
| `POST` | `/api/recordings/{id}/export` | Neu: Export-Caption-Video, Body: `{preset: string, language?: string, background_video?: url}` |
| `GET` | `/api/recordings/{id}/export/ass?preset=...` | Neu: Läd die `.ass`-Datei herunter (ohne Render) |
| *`GET`* | */api/templates* | Neu: Liste öffentlicher Templates |
| *`POST`* | */api/templates* | Neu: Eigenes Template erstellen/hochladen |
| *`PUT`* | */api/templates/{id}* | Neu: Template bearbeiten |
| *`DELETE`* | */api/templates/{id}* | Neu: Template löschen |
| *`POST`* | */api/templates/{id}/install* | Neu: Template installieren (ggf. mit Credits) |
| *`POST`* | */api/credits/transfer* | Änderung: Transfer an andere User (Template-Ersteller-Vergütung) |

### Drittanbieter-Credits

- Spätere Erweiterung: Drittanbieter können ihre Templates **gegen echtes Geld** 
  verkaufen (separater Change — dann brauchen wir Zahlungsabwicklung)

## Was NICHT geändert wird (Scope)

- Kein Video-Schnitt oder Szenen-Wechsel — pure Caption-Overlays
- Kein Remotion-Container (nur ASS/ffmpeg)
- Kein Echtzeit-Video-Streaming von Exporten
- Kein mobiler Render (Server-rendered, dann Download)

## Specs-Delta

- `ADDED` **caption-export**: Export-Modul (ASS-Generator, Preset-Manager, 
  Template-Engine, Render-Service)
- `MODIFIED` **recordings**: Recording bekommt Export-Endpoint + Export-Status
- `MODIFIED` **credits**: Credits-System wird um Template-Marktplatz-Transaktionen 
  erweitert
- `ADDED` **templates**: Template-Marktplatz-Capability (CRUD, Installation, Sharing, 
  Credits-Tausch)

## Risiken / Trade-offs

| Risiko | Maßnahme |
|--------|----------|
| ASS-Karaoke-Timing ist komplex | Presets kapseln die ASS-Logik, User müssen nur Parameter setzen |
| ffmpeg-Rendering verbraucht CPU | Separater Render-Container mit eigener CPU/Ressourcen-Limitierung |
| Credit-Tausch-Betrug (Credits waschen) | Maximal-Preis-Cap, Karma-System (später, erstmal Vertrauensbasis) |
| Template-Sicherheit (ASS-Injection) | ASS-Textfelder validieren/escapen, keine Shell-Befehle |
| Render-Latenz bei großen Videos | Progress-Reporting via WebSocket, asynchrones Rendern |