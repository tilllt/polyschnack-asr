# Change 057 — Re-Diarize: Sprecher-Zuordnung erneut berechnen

## Problem

Die Diarization (Sprecher-Zuordnung der Segmente) läuft heute nur beim
(Re-)Transkribieren mit `enable_diarize`. Danach gibt es **keine** Möglichkeit,
die Sprecher-Zuordnung zu korrigieren, ohne die komplette Transkription neu zu
rechnen (`retranscribe` verwirft Text, manuelle Segment-Aufteilung und
Alignment). User-Anfrage 2026-08-20: „könnte man auch eine re-diarize Funktion
einbauen, so wie re-transkribe und re-align?"

## Ziel

**„Re-Diarize"-Button** analog zu Re-Transcribe/Re-Align: startet **nur** die
Diarization auf dem vorhandenen Audio und ersetzt die `speaker`-Felder der
Segmente. **Text, Wörter, Timestamps, manuelle Segment-Aufteilung und
Alignment bleiben unangetastet.**

## Architektur

- **Muster: Change 046 (Re-Align)** — `POST /api/recordings/{rid}/realign`
  (recordings.py) mit Hintergrund-Worker (`_schedule_realign`, segments.py)
  und ehrlichem Status (`alignment`: done|pending|running|skipped). Re-Diarize
  übernimmt genau dieses Muster.
- **Neuer Endpunkt** `POST /api/recordings/{rid}/rediarize` (write-Zugriff
  wie Re-Align):
  1. Voraussetzungen: `status=done`, Audio vorhanden, Diar-Dienst erreichbar
     (sonst 409/503 mit klarer Meldung, analog Re-Align).
  2. Worker im Hintergrund: Diarization auf dem Audio über den bestehenden
     Diar-Dienst (`diarize_method` des Recordings, sonst Server-Default;
     Methoden pyannote|foxnose|energy|xcorr|vad-turns) → Sprecher-Intervalle
     → je Segment das `speaker`-Feld neu setzen (Segment-Mitte fällt in
     Sprecher-Intervall; unklar → `_none`).
  3. `rec.text`, `segments[].text/start/end/words` und `alignment` bleiben
     unverändert; `updated_at` wird gesetzt.
  4. **Ehrlicher Status** analog Alignment: neues Feld `diar_status`
     (done|pending|running|failed) + Heartbeat; Button disabled während
     running; Fehler sichtbar (Toast + `diar_status=failed`), kein stiller
     Fail, kein Fake-Fortschritt.
- **Frontend:** Button „Re-Diarize" neben Re-Transcribe/Re-Align in der
  Karten-Aktionsleiste — sichtbar bei `status=done` (write-Zugriff); wenn
  `enable_diarize` aus ist, wird es durch den Lauf implizit aktiviert
  (Dokumentation im Tooltip). i18n de/en/pt-BR.

## Requirements

- **REQ-UI-057-01:** Button „Re-Diarize" bei `status=done` (write-Zugriff),
  neben Re-Transcribe/Re-Align.
- **REQ-UI-057-02:** Es wird NUR die Sprecher-Zuordnung neu berechnet —
  Text, Wörter, Zeiten, manuelle Segmente und Alignment unverändert.
- **REQ-UI-057-03:** Hintergrund-Lauf mit ehrlichem Status
  (pending/running/done/failed + Heartbeat); kein Fake-Fortschritt.
- **REQ-UI-057-04:** Diar-Dienst nicht erreichbar → klare Meldung
  (409/503 + Toast), kein stiller Fehler.

## Nicht-Ziele

- Kein Ersatz für Re-Transcribe/Re-Align; keine Auto-Re-Diarize nach
  Segment-Edits.
- Kein Einfluss auf Benchmark-Ownership (Change 026).
