## MODIFIED Requirements

### Requirement: Export (Template-basiert)

- **Ablauf:** `GET /api/recordings/{id}/export?format=<template>&max_duration_s=…`
  lädt das Export-Template (Datei aus `DATA_DIR/export_templates/`,
  eingebaute Namen `txt|srt|vtt` lösen die Standard-Templates auf) und
  rendert die Transkription: `format_header` einmal voran, dann pro
  Segment eine Instanz von `format_paragraph` (Platzhalter ersetzt),
  danach `format_footer`. `max_duration_s` (optional, >0) teilt die
  Segmente vorher über `resegment_by_duration` in Blöcke ≤ N Sekunden —
  identisch zur GUI-Preview und zum bisherigen Verhalten.
- **Template-Modell (Datei, JSON):** `name`, `extension`,
  `format_header`, `format_paragraph`, `format_footer`,
  `format_timecode`, `format_newline` — Struktur kompatibel zu Subtitle
  Edit (`CustomFormatTemplate`), damit SE-Templates theoretisch direkt
  nutzbar sind.
- **Platzhalter (Header/Footer):** `{title}`, `{media-file-name}`,
  `{media-file-name-with-ext}`, `{#lines}`, `{#total-words}`,
  `{#total-characters}`, `{tab}`.
- **Platzhalter (Paragraph, pro Segment):** `{start}`, `{end}` (je im
  `format_timecode`-Format), `{text}`, `{text-csv}` (CSV-escaped),
  `{number}` (1-basiert), `{number-1}` (0-basiert), `{duration}`,
  `{actor}` (Sprecher-Label), `{actor-colon-space}` („SPEAKER_01: "),
  `{actor-upper-brackets-space}` („[SPEAKER_01] "), `{text-line-1}`,
  `{text-line-2}`, `{text-length}`, `{gap}`, `{bookmark}` (`*`),
  `{tab}`. Nicht unterstützt (kein Übersetzungspaar): `{original-text}`
  → leer. Unbekannte Platzhalter bleiben literal (kein stummer Fehler).
- **TimeCode-Syntax (`format_timecode`):** SE-kompatibel — `h`/`m`/`s`
  als Uhr-Komponenten (Doppelbuchstabe = zweistellig), `z` =
  Millisekunden-Bruchteil, `f` = Frames; führender Lauf aus `s`/`z`
  (≥2 oder komplett) = Gesamt-Sekunden/-Millisekunden („ss.zzz" →
  „61.160", „zzz" → „61160"); „ff" allein = Gesamt-Frames. Beispiele:
  `hh:mm:ss,zzz` (SRT), `hh:mm:ss.zzz` (VTT), `mm:ss,ff`.
- **NewLine (`format_newline`):** `{newline}` = System-Newline,
  `{lf}` = `\n`, `{cr}` = `\r`, `{tab}` = `\t`; der Sonderwert
  `[Do not modify]` lässt Zeilenumbrüche im Text unverändert.
- **Ablage & Verwaltung:** Standard-Templates (`srt`, `vtt`, `txt`)
  werden beim Start nach `DATA_DIR/export_templates/` geschrieben, falls
  nicht vorhanden; eigene Templates = Datei anlegen (kein Rebuild).
  `GET /api/export-templates` listet Name + Endung aller verfügbaren
  Templates (für das UI-Dropdown).
- **Architektur:** `export.py` (Template-Renderer, Loop über
  `format_paragraph`), `routers/recordings.py` (Export-Route),
  `service.py` (`resegment_by_duration` bleibt Vorverarbeitung);
  Frontend-Dropdown in der Recording-Karte.
- **Fehlerbehandlung:** Fehlendes Template → 404; kaputtes Template
  (fehlende Pflichtfelder/ungültiges JSON) → 500 mit Fehlermeldung im
  Body; Export bleibt UTF-8 (`charset=utf-8` wie bisher).

#### Scenario: SRT-Export unverändert wie bisher

- **Akteure:** Besitzer oder Share mit Zugriff.
- **Eingaben:** `export?format=srt` bei einer 2-Segment-Transkription
  mit Sprecher-Labels.
- **Ergebnis:** Ausgabe identisch zum bisherigen `to_srt`
  (Golden-Test): `1\n00:00:00,000 --> 00:00:05,000\n[SPEAKER_01] Text…`
  — das eingebaute `srt.json`-Template erzeugt Byte-gleichen Inhalt.

#### Scenario: Eigenes Template (YouTube-Transcript-Stil)

- **Akteure:** Admin.
- **Eingaben:** Neue Datei `DATA_DIR/export_templates/youtube.json`
  mit `format_paragraph` = `{start} {end}\n{text}\n` und
  `format_timecode` = `hh:mm:ss`.
- **Ergebnis:** `GET /api/export-templates` listet „youtube";
  `export?format=youtube` liefert pro Segment eine Zeile
  `HH:MM:SS HH:MM:SS\nText…`.

#### Scenario: Segmentlänge beim Export berücksichtigt

- **Akteure:** Besitzer.
- **Eingaben:** `export?format=srt&max_duration_s=30` bei einem
  105-s-Segment.
- **Ergebnis:** Wort-Timestamps werden in Blöcke ≤ 30 s aufgeteilt
  (identisch zur Preview); SRT enthält mehrere Einträge statt eines
  Riesen-Segments.

#### Scenario: Kaputtes Template meldet Fehler

- **Akteure:** Besitzer.
- **Eingaben:** `export?format=kaputt` (Datei fehlt) bzw. Template mit
  ungültigem JSON.
- **Ergebnis:** 404 (fehlt) bzw. 500 mit Fehlermeldung im Body —
  kein stiller, unvollständiger Download.
