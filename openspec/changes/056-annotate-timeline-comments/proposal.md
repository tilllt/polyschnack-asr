# Change 056 — Annotate: zeitgebundene Kommentare zur Transkription

## Problem

Bei schwierigen Passagen (unverständliche Wörter, Dialekt, historische
Aufnahmen — Walzen/Schellack aus Change 025) gibt es heute keine Möglichkeit,
kontextuelle Notizen zu hinterlassen. Die Text-Markierung bietet nur
**Insert Segment** (Split). Für den Ground-Truth-Workflow fehlt ein
Kommentar-Kanal: Die Projektleitung markiert unklares Audio, ein Zweiter
recherchiert und antwortet — ohne dass die Notiz an der **Zeitposition**
hängt oder beim Abspielen sichtbar wird.

## Ziel (wörtliche User-Vorgabe, 2026-08-20)

1. Wenn man eine **Passage markiert**, erscheinen zwei Kontext-Funktionen:
   **Insert Segment** (wie gehabt) + **Annotate**.
2. **Annotate**: Kommentar-Eingabe wie bei PDF-Annotationen.
3. Notizen zu schwer verständlichen Wörtern o. ä.; **andere User können
   antworten** (Threads).
4. **Markdown** wird unterstützt.
5. SoundCloud-artig: Die Annotation hängt an der markierten **Zeitposition**.
6. Die **Position der Annotationen wird auf der WaveSurfer-Timeline
   angezeigt**.
7. Läuft das **Playback über eine Annotation** (Zeitfenster), wird diese
   angezeigt (Bubble/Highlight — SoundCloud-Prinzip).

## Architektur

### Datenmodell (Backend, SQLModel — neue Tabelle `annotation`)

| Feld | Typ | Bedeutung |
|---|---|---|
| id / uid | int / str | PK + externer Referenz |
| rec_id | int (FK Recording) | Aufnahme |
| user_id | int (FK User) | Autor |
| segment_idx | int | Segment der Markierung |
| char_start / char_end | int | Zeichen-Range im Segment-Text (aus dem bestehenden Markierungs-System) |
| start_s / end_s | float | Zeitfenster — aus den Wort-Timestamps der Markierung abgeleitet (Change 010; Fallback: Segment-Grenzen) |
| body | text | Kommentar (Markdown) |
| parent_id | int, nullable | Antwort = Thread; null = Top-Level-Annotation |
| created_at / updated_at | datetime | Sortierung + „zuletzt bearbeitet" |

Neue Tabelle → `SQLModel.metadata.create_all` legt sie beim Start an
(bestehende Tabellen unberührt; Auto-ALTER aus db.py greift nur für
Spalten, hier nicht nötig).

### API (Router `annotations.py`, Prefix `/api`)

- `GET /api/recordings/{uid}/annotations` → flache Liste (Frontend baut
  Threads über parent_id); **read**-Zugriff wie Transkription.
- `POST /api/recordings/{uid}/annotations` → Body
  `{segment_idx, char_start, char_end, body}`; Server berechnet start_s/end_s
  aus den Segment-Wörtern (Fallback Segment-Grenzen); **write**-Zugriff
  (wie Segment-Edit/Tags).
- `POST /api/annotations/{aid}/replies` → Antwort (parent_id, write).
- `PATCH /api/annotations/{aid}` → Body-Edit (Autor oder Admin).
- `DELETE /api/annotations/{aid}` → löscht Thread-Kaskade (Antworten
  inklusive), Autor oder Admin.

### Frontend

- **Kontext-Leiste bei Markierung:** Das bestehende Split-Symbol
  (splitAnchor, SegmentList.tsx) wird zur kleinen Kontext-Leiste mit zwei
  Aktionen: **Insert Segment** (öffnet das bisherige Sprecher-Popover
  unverändert) und **Annotate** (neues Popover mit Textarea + Hinweis
  „Markdown unterstützt"). Beide teilen sich die Markierungs-Koordinaten
  (idx, charStart, charEnd) — kein zweites Markierungs-System.
- **Annotation-Threads (Anzeige):** Eigener Bereich im Recording-Detail
  (unterhalb der Transkription): Top-Level-Kommentar mit Avatar/Name,
  Datum, Zeitfenster-Chip (`0:42–0:47`), Antworten eingerückt,
  Antwort-Formular. **Markdown-Rendering** via `react-markdown` (neue
  Dependency; kleines, sicheres Rendering — kein dangerouslySetInnerHTML).
  **Mentions:** `@name`-Token werden beim Rendern erkannt und als
  User-Link dargestellt (hervorgehobener Chip); Klick auf eine Erwähnung
  öffnet das Antwort-Formular mit `@name ` vorbelegt. **Kein
  Benachrichtigungs-Versand** (E-Mail/Push) — bewusst ausgeklammert.
- **Timeline-Marker:** WaveSurfer 7.x hat **kein** Markers-Plugin (erst 8.x;
  ein 8er-Upgrade wäre ein Breaking-Change-Risiko für die erprobte
  Regions/Timeline/Hover/MediaElement-Integration). Stattdessen **Overlay
  im Timeline-Container**: 💬-Elemente absolut positioniert mit
  `left = start_s/duration·100 %` → bleiben bei Zoom (Timeline-Breite
  wächst) und Scroll (Container) korrekt; Klick → Annotation scrollt ins
  Bild + Highlight. (Nebenbei: wavesurfer 7.8.0 → 7.12.11 aktualisiert.)
  Marker je Top-Level-Annotation (Antworten erben das Fenster).
- **Playback-Trigger:** Der bestehende `onTimeUpdate`-Strom (WaveformPlayer)
  prüft im Recording-Detail: Liegt `currentTime` im Fenster `[start_s, end_s]`
  einer Annotation → diese wird als **SoundCloud-Bubble** über der Timeline
  angezeigt (automatisch ein-/ausgeblendet beim Verlassen des Fensters) und
  in der Thread-Liste hervorgehoben. Aktive Bubble klickbar → Annotation.
- **Aktualisierung:** Nach Anlage/Bearbeitung/Löschung Query-Invalidate
  (`["annotations", uid]`), gleiches Muster wie Tags.
- i18n de/en/pt-BR („Annotate", „Antworten", „Markdown unterstützt", …).

## Requirements

- **REQ-UI-056-01:** Markierung zeigt beide Kontext-Aktionen — Insert
  Segment (unverändert) und Annotate.
- **REQ-UI-056-02:** Annotate-Popover mit Kommentar-Eingabe; Speichern
  verknüpft die Annotation mit dem Zeitfenster der Markierung.
- **REQ-UI-056-03:** Threads: Antworten anderer User, eingerückt; Autor/
  Admin können editieren/löschen.
- **REQ-UI-056-04:** Markdown in body (Rendering, kein HTML-Injection).
- **REQ-UI-056-05:** Marker je Annotation auf der WaveSurfer-Timeline;
  Klick springt zur Annotation.
- **REQ-UI-056-06:** Playback über ein Annotation-Fenster zeigt die
  Annotation an (Bubble + Listen-Highlight); beim Verlassen verschwindet sie.
- **REQ-UI-056-07:** Lese-Zugriff = Transkriptions-Zugriff; Schreiben/
  Antworten = write (Owner/Share) — konsistent zu Tags/Segment-Edit.
- **REQ-UI-056-08:** Mentions: `@name` in body wird als hervorgehobener
  User-Link gerendert; Klick belegt das Antwort-Formular mit `@name `.
  **Kein** Benachrichtigungs-Versand (kein E-Mail/Push).

## Nicht-Ziele

- Kein Benachrichtigungs-Versand für Mentions (E-Mail/Push) — Mentions
  sind reine Inline-Referenzen; Versand wäre ein Folge-Change.
- Keine Annotations-Suche/Filtermöglichkeit (nur Liste nach Zeit sortiert).
- Kein Annotieren per Drag auf der Waveform (nur via Text-Markierung).
- Kein Einfluss auf Benchmark-Ownership (Change 026) — Annotationen sind
  Arbeitsnotizen, keine Ground-Truth-Daten.
