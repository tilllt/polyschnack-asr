# Change Proposal 008 — Template-basierter Export (Subtitle-Edit-kompatibel)

**Status:** Proposed

## Why

Der Export ist heute auf drei hartkodierte Formate fixiert
(`to_txt` / `to_srt` / `to_vtt` in `service.py`, Auswahl über
`GET /api/recordings/{id}/export?format=txt|srt|vtt`). Jedes neue
Zielformat (YouTube-Transcript, Audacity-Labels, CSV, FCP-Marker,
Eigene Schnittlisten…) erfordert Code-Änderung + Rebuild + Redeploy.

**Ziel:** Exportformate werden zu **Template-Dateien mit Platzhaltern**,
über die pro Segment geloopt wird — analog zu Subtitle Edit
(`CustomFormatTemplate` / `CustomTextFormatter`). Damit lassen sich
neue Formate ohne Code-Änderung hinzufügen (auch durch Admins/User),
und **Templates aus Subtitle Edit sind theoretisch direkt nutzbar**
(Platzhalter-Vokabular + TimeCode-Syntax sind 1:1 kompatibel).

## What

### Template-Modell (analog SE `CustomFormatTemplate`)
Jedes Export-Template ist eine Datei (JSON, einfach erweiterbar) mit:

- `name` — Anzeigename (z. B. „SubRip (SRT)")
- `extension` — Dateiendung (z. B. `srt`)
- `format_header` — einmaliger Kopf (dokumentiert: `{title}`,
  `{media-file-name}`, `{#lines}`, `{#total-words}`,
  `{#total-characters}`, `{tab}`)
- `format_paragraph` — pro Segment geloopt (dokumentiert: `{start}`,
  `{end}`, `{text}`, `{number}`, `{number-1}`, `{duration}`, `{actor}`,
  `{actor-colon-space}`, `{actor-upper-brackets-space}`, `{text-line-1}`,
  `{text-line-2}`, `{text-length}`, `{gap}`, `{text-csv}`, …)
- `format_footer` — einmaliger Fuß
- `format_timecode` — Zeitformat-Zeichenkette (SE-Syntax:
  `hh:mm:ss,zzz`, `hh:mm:ss.zzz`, `ss.zzz`, `mm:ss,ff`, `zzz` … mit
  h=Stunden, m=Minuten, s=Sekunden, z=Bruchteil, f=Frames; führender
  s/z-Lauf = Gesamt-Sekunden/-Millisekunden)
- `format_newline` — Zeilenumbruch-Ersetzung (`{newline}`, `{tab}`,
  `{lf}`, `{cr}`; `[Do not modify]` = unverändert)

### Plattform-Anpassungen (Abweichungen zu SE, dokumentiert)
- `{actor}` = Sprecher-Label (`speaker`-Feld, z. B. `SPEAKER_01`);
  SEs `{original-text}` bleibt leer (kein Übersetzungs-Paar);
  `{bookmark}` = `*` (kein Konzept in der App).
- `max_duration_s` (Re-Segmentierung ≤ N Sekunden) bleibt als
  **Vorverarbeitungs-Option** erhalten — identisch zur GUI-Preview und
  zum heutigen Export (gleiche Funktion `resegment_by_duration`).

### Ablage, API & UI
- **Ablage:** `DATA_DIR/export_templates/*.json` — gebündelte
  Standard-Templates (srt, vtt, txt) beim Start, falls fehlend.
  Eigene Templates durch Datei-Anlage (Admin) — kein Code-Rebuild.
- **API:** `GET /api/export-templates` (Liste: name, extension);
  `GET /api/recordings/{id}/export?format=<template>&max_duration_s=…`
  nutzt das Template (Rückwärts-kompatibel: `txt|srt|vtt` lösen die
  eingebauten Templates auf).
- **UI:** Export-Dropdown listet alle Templates (Name + Endung);
  Auswahl + optionale Segmentlänge → Download wie bisher.

## Changes

- **Neu:** `export_templates/`-Verzeichnis mit Standard-Templates
  (`srt.json`, `vtt.json`, `txt.json` — SRT/VTT äquivalent zu heute);
  `export.py::render_template(template, segments, meta)` (Loop über
  `format_paragraph` mit `string.format`-Mapping wie SE).
- **Geändert:** `service.py` (`to_srt/to_vtt/to_txt` werden durch
  Template-Renderer ersetzt bzw. delegieren an die eingebauten
  Templates), `routers/recordings.py` (Export-Route liest Template),
  Frontend-Export-Dropdown.
- **Tests:** Template-Render (Platzhalter, TimeCode-Syntax, Loop,
  Header/Footer, NewLine), SRT/VTT-Äquivalenz zu den heutigen
  Ausgaben (Golden-Tests), `max_duration_s`-Kombination,
  unbekannter Platzhalter = literal, kaputtes Template → 500 mit
  Fehlermeldung (kein stummer Fehler).

## Downgrade

- Zurück zu hartkodierten `to_txt/to_srt/to_vtt`; Templates werden
  ignoriert; Export-Route wie vor Change 008.
