# Change 056 — Tasks

## Phase 1: Backend (Modell + API)
- [x] `models.py`: Tabelle `Annotation` (rec_id, user_id, segment_idx,
      char_start, char_end, start_s, end_s, body, parent_id, created_at,
      updated_at) + Serialisierung
- [x] `routers/annotations.py`: GET-Liste (read), POST (write; start_s/end_s
      aus Segment-Wort-Timestamps ableiten, Fallback Segment-Grenzen),
      POST replies, PATCH (Autor/Admin), DELETE (Thread-Kaskade)
- [x] Auth konsistent: `ensure_access` read/write wie Segment-Edit/Tags
- [x] Backend-Tests: CRUD, Zeit-Ableitung (mit/ohne Wort-Timestamps),
      Antworten (parent_id), Rechte (fremder User → 403), Thread-Löschung

## Phase 2: Frontend (Markierung → Annotate)
- [x] `react-markdown` als Dependency (package.json)
- [x] Kontext-Leiste: splitAnchor-Symbol → Leiste mit „Insert Segment"
      (bestehendes Popover) + „Annotate" (neues Popover mit Textarea)
- [x] Annotate-Popover: Kommentar-Eingabe, Speichern → POST, sichtbares
      Feedback (Toast), Fehler kein stiller Fail
- [x] `api.ts`: Annotation-Typ + fetch/create/reply/update/delete

## Phase 3: Frontend (Anzeige, Timeline, Playback)
- [x] Thread-Bereich im Recording-Detail: Liste nach Zeit sortiert, Antworten
      eingerückt, Markdown-Rendering, Antwort-Formular, Edit/Delete (nur
      Autor), Zeitfenster-Chips
- [x] Mentions: `@name`-Token → hervorgehobener User-Link; Klick belegt
      Antwort-Formular mit `@name ` (kein Versand/E-Mail)
- [x] WaveformPlayer: 💬-Marker je Top-Level-Annotation an start_s als
      Overlay im Timeline-Container (wavesurfer 7.x hat KEIN Markers-Plugin
      — erst 8.x; ein 8er-Upgrade wäre Breaking-Change-Risiko für
      Regions/Timeline/Hover/MediaElement. Overlay: left% = start_s/dur →
      bleibt bei Zoom/Scroll korrekt). Klick → Annotation hervorheben
      (wavesurfer 7.8.0 → 7.12.11 aktualisiert)
- [x] Playback-Trigger: onTimeUpdate prüft Annotation-Fenster → Bubble über
      der Timeline (SoundCloud-Stil) + Highlight in der Liste; Ausblenden
      beim Verlassen
- [x] Query-Integration (`["annotations", uid]`), i18n de/en/pt-BR
- [x] Frontend-Tests: Kontext-Leiste (2 Aktionen), Annotate-Speichern,
      Markdown-Rendering, Marker-Klick, Playback-Trigger (Fenster rein/raus)

## Phase 4: Qualität
- [x] tsc --noEmit sauber, vitest + Backend-Suite grün
- [ ] OpenSpec-Proposal auf Ist-Stand abgleichen, Commit + Push, CI prüfen
