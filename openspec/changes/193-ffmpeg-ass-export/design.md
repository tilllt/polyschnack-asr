# Design — Change 193

## Architektur-Übersicht

```
PolySchnack Webapp (Kern)
  │
  ├─ Export-Button (RecordingCard.tsx)
  │   → POST /api/recordings/{id}/export
  │
  ├─ ASS-Generator (app/export/ass_generator.py)
  │   Nimmt: Caption-Daten + Template-ID + Optionen
  │   Gibt: .ass-String (oder Datei)
  │   └─ Nutzt: app/export/template_engine.py (Platzhalter-Ersetzung)
  │
  ├─ Preset-Manager (app/export/presets.py)
  │   Lädt: Standard-Presets aus export/presets/*.ass
  │   Lädt: User-Templates aus DB (templates-Tabelle)
  │
  ├─ Template-API (app/routers/templates.py)
  │   CRUD für Templates, Installation, Sharing
  │   └─ DB: Tabelle templates + template_installations + template_credits
  │
  └─ Render-Client (app/export/render_client.py)
      Optional: Sendet .ass + Video/Background an ps-render-Container
      └─ Nur aktiv, wenn COMPOSE_PROFILE render gesetzt ist

ps-render Container (optional)
  ├─ API: POST /render → ffmpeg -i bg_video -vf ass=/tmp/output.ass output.mp4
  ├─ Benötigt: ffmpeg (mit libass) + empfängt background + .ass
  └─ Liefert: Fortschritt via WebSocket + finales MP4 via Download-Link
```

## Datenmodell (DB-Erweiterungen)

### Tabelle `templates`

```sql
CREATE TABLE templates (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags TEXT[] DEFAULT '{}',
    ass_template TEXT NOT NULL,         -- ASS-Vorlage mit Platzhaltern
    parameters JSONB DEFAULT '{}',       -- Default-Parameter (Farbe, Größe, Position)
    thumbnail_url TEXT,                  -- Vorschau-Bild (optional)
    visibility TEXT DEFAULT 'private',   -- 'private' | 'public' | 'link_only'
    credit_cost INTEGER DEFAULT 0,       -- 0 = kostenlos, >0 = Credits
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Tabelle `template_installations`

```sql
CREATE TABLE template_installations (
    id UUID PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES templates(id),
    user_id UUID NOT NULL REFERENCES users(id),
    installed_at TIMESTAMP DEFAULT NOW(),
    credit_spent INTEGER DEFAULT 0,      -- Wie viele Credits gezahlt
    current_version INTEGER DEFAULT 1    -- Version bei Installation
);
```

### Tabelle `credit_transfers` (erweitert)

```sql
-- Bestehende Tabelle, neuer Transfer-Typ:
ALTER TABLE credit_transfers ADD COLUMN template_id UUID REFERENCES templates(id);
-- template_id gesetzt → dieser Transfer ist eine Template-Vergütung
```

## ASS-Template-Engine

User schreiben `.ass`-Vorlagen. Platzhalter werden ersetzt:

```
{{#words}}
Dialogue: 0,{{start_ms}},{{end_ms}},Default,,0,0,0,,{{\c&H{{current_color}}&}}{{word}}{{\c&H{{rest_color}}&}} {{prev_words}}
{{/words}}
```

Erweiterte Template-Engine mit:
- **Schleifen:** `{{#words}}...{{/words}}` — iteriert über jedes Wort
- **Bedingungen:** `{{#is_highlight}}...{{/is_highlight}}`
- **Parameter:** User-definierte Parameter werden vor dem Rendern erfragt
- **Filter:** `{{uppercase(word)}}`, `{{lowercase(word)}}`

Die Engine verwendet **Jinja2** (Python, bereits in PolySchnack-Dependencies) — 
keine neue Abhängigkeit.

## Standard-Presets

Die 5 Presets liegen als `.ass.j2`-Dateien unter `app/export/presets/`:

- `classic.ass.j2` — weiß, unten, Outline
- `karaoke.ass.j2` — `\k`-Timing für Farbverlauf
- `highlight.ass.j2` — aktives Wort farbig, Rest transparent
- `kinetic.ass.j2` — `\move()` + `\t(\fscy)` für Popping-Effekt
- `modern.ass.j2` — große Schrift, zentriert, Wort-für-Wort

Jedes Preset-Jinja2-Template hat einen YAML-Header mit Default-Parametern:

```yaml
# preset.yaml
name: Highlight
description: Aktuelles Wort farbig, vorherige ausgegraut
parameters:
  primary_color: "Hffffff"     # aktives Wort (BGR!)
  dim_color: "H888888"         # vorherige Wörter
  font_size: 48
  font_name: Arial
  position_y: 600              # absolute Y-Position
  alignment: 2                 # 2=center, 1=left, 3=right
```

## Render-Fluss (Video-Export)

1. User drückt Export → Dialog mit Preset-Auswahl + ggf. Background-Video
2. Webapp generiert `.ass`-Datei (Template → Caption-Daten)
3. **Fall A (ASS-Download):** `.ass` als Datei zurückgeben → User kann selbst brennen
4. **Fall B (MP4-Render):**
   - Webapp schickt `.ass` + Background-Video (oder Recording-Video) an 
     ps-render-Container
   - ps-render führt `ffmpeg -i bg.mp4 -vf "ass=/tmp/subtitles.ass" output.mp4` aus
   - Fortschritt per WebSocket (falls lang)
   - Fertiges MP4 wird per Download-Link bereitgestellt (temp-URL, 24h gültig)
5. Nach Render: Aufräumen (temp-Dateien löschen)

## Credits-Tausch-Fluss

1. User A erstellt Template, setzt `credit_cost = 5`, `visibility = public`
2. User B installiert es → `POST /api/templates/{id}/install`
3. Backend prüft: B hat ≥5 Credits? A blockiert nicht?
4. 5 Credits von B → 4.5 zu A, 0.5 Plattform-Anteil (10 %)
5. DB: template_installations-Eintrag + credit_transfer-Eintrag
6. B bekommt das Template in seiner Bibliothek (auch nach Credit-Änderung)

## Offene Design-Fragen

1. **Template-Versionierung:** Soll ein Update des Templates automatisch bei 
   allen Installateuren landen? → Nein (sicherheits-kritisch). Aber Update-Hinweis 
   im Export-Dialog: "Template X hat Version 3 — Sie haben Version 1. Update?"
2. **Karma-System:** Spam-Templates? → Erstmal manuelles Reporting, später 
   automatisierte Qualitäts-Prüfung (Check: mindestens 1 Wort-Dialogue vorhanden)
3. **Konkurrierende Render-Jobs:** Queue oder parallel? → Queue (1 Job, wie 
   Transkription), da CPU-Intensiv
4. **Background-Video:** Nur User-Uploads? Oder Standard-Farbverlauf? → 
   Standard: simpler Farbverlauf (Blau↔Weiß) oder User wählt Hintergrund-Farbe/Schrift