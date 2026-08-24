# Change 115 — Live-Progress & RTF-Ausgaben bei Hintergrund-Vorgängen

## Proposal

### Problem (User-Befund, 24.08.)

„Der neue Heartbeat/Progress-Mechanismus und RTF-Learner-Ausgaben sollen bei
ALLEN Vorgängen angezeigt werden. Re-Align zeigt nur 'Präzises Alignment
läuft im Hintergrund …'."

Ist-Zustand:
- Der Live-Progress-Block (Phasen-Chips, `phaseDetail`, Heartbeat-Ampel,
  ETA) wird in `RecordingCard.tsx` nur bei `r.status === "processing"`
  gerendert (Z. 1390).
- Bei `status === "done" && alignment === "running"` (Z. 1231) und
  `diar_status === "running"/"pending"` (Z. 1255) gibt es nur statische
  Texte — obwohl der Align-Worker längst echte Daten schreibt:
  - `set_progress(...)` (service.py Z. 744/805/867) tickt `last_heartbeat_at`
    (crud.py Z. 549) und setzt Noten `"alignment Gruppe 3/12 — aktiv seit
    42s — CLI 45%"`.
  - `learner_store.ingest_align_sample(...)` (Z. 904) sammelt Align-RTF.
- Re-Diarize-Worker tickt `last_heartbeat_at` NICHT (setzt progress_note
  direkt, Z. 1371) → die UI könnte nie „aktiv seit" zeigen.

### Design

**Frontend (RecordingCard):**
- Die Hintergrund-Hinweise (align running / rediarize running) rendern
  echte Live-Details statt statischem Text:
  - Heartbeat-Ampel (`hb.level`: ok/warn/stalled) + „Heartbeat vor Xs"
  - `phaseDetail` bei Align („Gruppe 3/12 — aktiv seit 42s — CLI 45%" —
    enthält die RTF-Learner-Ausgabe des Aligners)
  - „aktiv seit Xs" aus `hb.sinceBeat` bei Re-Diarize
- Kein Fake-Progress: pct bleibt unverändert (Align: 96, Re-Diarize: kein
  pct-Tick), nur echte Backend-Felder (last_heartbeat_at, progress_note).
- Keine Fake-ETA für Align/Re-Diarize (kein Dauer×RTF-Modell) — „aktiv
  seit" statt ETA, wie bei processing ohne etaRange.

**Backend (service.py):**
- Re-Diarize-Worker: `_start_job_heartbeat(rec_id)` starten (tickt
  last_heartbeat_at via set_progress mit note=None — crud Z. 550 lässt die
  Note unangetastet), Stop im finally. Der Align-Worker tickt bereits über
  seine set_progress-Aufrufe.
- Re-Diarize: RTF-Stichprobe sammeln (diar-Phasen-Zeit →
  `learner_store.ingest_job_sample` bzw. analog align) — gleiche Datenbasis
  wie der Haupt-Job (diar:{method}).

### Nicht-Ziel

- Kein neues ETA-Modell für Align/Diarize (würde Fake-Präzision erzeugen).
- Keine Änderung am Haupt-Job-Progress (funktioniert bereits).
- Kein Umbau der Phasen-Chips (nur die Hintergrund-Hinweise werden live).

### Verifikation

- Frontend-Test: bg-align-Hinweis rendert phaseDetail + Heartbeat-Zeit;
  bg-diar-Hinweis rendert „aktiv seit".
- Backend-Test: Re-Diarize-Worker tickt last_heartbeat_at (set_progress-
  Aufruf im Worker) — oder Code-Review + Service-Test.
- Nach Deploy: Re-Align auf saisoncouplet → Hinweis zeigt „Gruppe X/Y —
  aktiv seit Xs — CLI 45%" statt statischem Text.
