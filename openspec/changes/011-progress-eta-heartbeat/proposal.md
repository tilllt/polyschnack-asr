# Change Proposal 011 — Fortschritt, ETA & Heartbeat (Status-Overhaul)

**Status:** Proposed

## Why

Nutzer wissen bei PolySchnack an vielen Stellen nicht, **was gerade passiert**
und **wie lange es dauert**. Ist-Analyse 2026-08-17 (Backend + Frontend + Queue):

1. **Queue unsichtbar:** `queue.list()` kennt Position + `eta_s`, aber die
   Recording-Serialisierung (`_recording_to_dict`) liefert kein einziges
   Queue-Feld. Eine Aufnahme, die hinten in der Warteschlange steht, zeigt
   dem Nutzer nur „Processing … 1%" — ohne Position, ohne Wartezeit, ohne
   Hinweis, dass sie gar nicht erst verarbeitet wird.

2. **ETA verschwindet in der langsamsten Phase:** Der Progress-Render
   (RecordingCard Z. 912) blendet die ETA bei gesetztem `phaseDetail`
   komplett aus: `{r.progress_pct}%{phaseDetail ? "" : " · " + eta}`.
   Genau in der Alignment-Phase (10–25 min, „Gruppe 3/12 — aktiv seit 42 s")
   sieht der Nutzer weder Fortschrittssprung noch Zeitangabe.

3. **Clientseitige Raten-Rate:** `etaFromRate`/`updateEta` extrapolieren
   nur aus Poll-Sprüngen. Bei pct=1 (Anlauf), pct=21 (Sync-Backends wie
   CrispASR hängen starr bei „asr") oder Phase ohne Rate steht dort nur
   „…" — dauerhaft.

4. **Kein serverseitiger ETA-Schätzer für laufende Jobs:**
   `avg_recent_processing_ms` wird nur für **queued** Jobs genutzt
   (`queue.list()` Z. 217); für laufende gibt es nichts außer der
   Client-Rate.

5. **Heartbeat nur für Alignment:** Der Aligner-Heartbeat (service.py
   Z. 599–648, „Gruppe x/y — aktiv seit Ns — CLI p% · letzte Zeile") ist
   der einzige Aktivitäts-Nachweis. Diarization (minutenlang bei 96%) und
   Sync-ASR (minutenlang bei 21%) zeigen **keine Lebenszeichen** — die UI
   wirkt eingefroren, obwohl der Worker rechnet. Der User wünscht explizit:
   „man kann sehen, dass noch etwas passiert, selbst wenn es noch keinen
   messbaren Fortschritt gibt."

**Ziel:** Jeder Zustand (queued / anlaufend / verarbeitend / phase / fertig)
zeigt **Phase + ETA + Aktivität**. Kein „…" mehr als Dauerzustand; wenn kein
Fortschritt messbar ist, zeigt ein **Heartbeat**, dass der Job lebt.

## What

### A) Serverseitige Phasen-Zeitstempel + Heartbeat-Felder (Backend)

Neue Felder auf `Recording` (Auto-Migration wie `segments_manual`, Change 009):

- `phase_started_at: Optional[datetime]` — Beginn der aktuellen Phase
  (gesetzt, wenn sich `progress_note` ändert).
- `last_heartbeat_at: Optional[datetime]` — letzter Aktivitäts-Nachweis
  (jeder `set_progress`-Aufruf aktualisiert ihn; zusätzlich tickt ein
  Heartbeat-Thread in Phasen ohne Fortschritt).

`crud.set_progress` wird erweitert: setzt `progress_pct` + `progress_note`
(wie bisher) UND `last_heartbeat_at = now`; bei Phasenwechsel
(neue `note` != alte) zusätzlich `phase_started_at = now`.

### B) Heartbeat-Threads für stille Phasen (Backend)

Das Aligner-Muster wird verallgemeinert (eine Helfer-Funktion):

- **Sync-ASR** (`async_jobs=False`, z. B. CrispASR-Familie, service.py
  Z. 845–852): läuft minutenlang bei „21% asr" — Heartbeat-Thread pollt
  nichts (kein Status-Endpoint), schreibt aber alle 5 s
  `set_progress(21, note="asr")` → `last_heartbeat_at` tickt → UI zeigt
  „transcribing · aktiv seit 3m" statt eingefrorenem 21 %.
- **Diarization** (service.py Z. 876): Heartbeat alle 5 s bei 96 %
  („diarization · aktiv seit 2m").
- **Alignment** bleibt wie ist (pollt echten `/status` des Aligners).

Kein erfundener Fortschritt: `progress_pct` bleibt konstant, nur
`last_heartbeat_at` tickt. Die UI übersetzt „frischer Heartbeat ohne
pct-Sprung" in eine Puls-Animation + „aktiv seit Xs".

### C) Queue-Position + Warte-ETA auf der Recording-Karte (Backend + Frontend)

- `_recording_to_dict` ergänzt für `status == "queued"` (und „processing"
  mit Warteschlange davor):
  - `queue_position: int` (aus `queue_manager.position(rec.id)`),
  - `queue_eta_s: Optional[int]` (`position × avg_recent_processing_ms`),
  - `queue_backend: str`.
- Frontend (RecordingCard): bei `queued` zeigt die Karte statt Spinner:
  „Warteschlange · Position 2 · ~3m · Backend" mit eigener Progress-Skala
  (Position/Backend-Kapazität), ETA aus `queue_eta_s`.

### D) ETA nie mehr ausblenden, Heartbeat-Anzeige (Frontend)

RecordingCard Progress-Render wird umgebaut:

- **ETA-Zeile immer:** `{pct}% · {eta}` — auch bei `phaseDetail` (Alignment).
- **ETA-Quellen-Hierarchie:**
  1. `queue_eta_s` (queued, serverseitig),
  2. Rate-Extrapolation (wie bisher, bei echten Sprüngen),
  3. Phasen-Rest-Fallback: „Phase läuft seit Xs" (aus `phase_started_at`),
     statt „…".
- **Heartbeat-Puls:** ist `last_heartbeat_at` jünger als ~8 s und hat sich
  `progress_pct` nicht bewegt → Puls-Animation auf der Progress-Bar
  (eigene CSS-Klasse `animate-pulse` auf dem Füllbalken) + „aktiv seit Xs".
- **Stall-Warnung:** ist `last_heartbeat_at` älter als ~45 s bei
  `status == "processing"` → Warnzeile „keine Aktivität seit Xs" (gelb,
  nicht rot — kein Fake-Fehler). Damit sieht man auch einen hängenden Job.

### E) Phasen-Skala dokumentieren & vereinheitlichen

`set_progress`-Noten werden konsistent (Doku im Service-Modul):
`preparing (10) → vad (12) → enhance (16) → asr (20/21) → [diarization
(96)] → [alignment (96–99)] → finalizing (95) → done (100)` — die UI-Mapping
(`NOTE_LABELS` + `phaseKey`) bleibt, bekommt aber den Heartbeat-Fallback.

## Changes

- **Geändert:** `webapp/app/models.py` (2 Felder + Auto-Migration),
  `webapp/app/crud.py` (`set_progress` mit Heartbeat/Phasenwechsel),
  `webapp/app/routers/recordings.py` (`_recording_to_dict`: Queue-Felder +
  Heartbeat-Felder), `webapp/app/service.py` (Heartbeat-Helfer +
  Einsatz in Sync-ASR/Diarization), `webapp/frontend/src/components/
  RecordingCard.tsx` (ETA immer, Heartbeat-Puls, Stall-Warnung,
  Queue-Anzeige), `webapp/frontend/src/api.ts` (Recording-Interface).
- **Tests (pytest, `webapp/tests/`):**
  - `set_progress` aktualisiert `last_heartbeat_at`; Phasenwechsel setzt
    `phase_started_at`; gleiche Note lässt `phase_started_at` stehen.
  - `_recording_to_dict` liefert `queue_position`/`queue_eta_s` bei queued.
  - Heartbeat-Thread (Sync-ASR): `last_heartbeat_at` tickt während eines
    gemockten, blockierenden `transcribe()`.
- **Tests (vitest):** ETA-Zeile erscheint auch mit `phaseDetail`;
  Heartbeat-Puls nur bei frischem Heartbeat; Stall-Warnung nur bei altem.
- **OpenSpec:** Deltas in `backend-queue` (Req 4: Recording-API liefert
  Queue-Felder) und `transcription-view` (Req 11: Fortschritts-Anzeige).

## Downgrade

- Felder entfernen, `set_progress` zurück auf pct+note, Heartbeat-Threads
  ausbauen, Frontend auf Stand vor Change 011 (ETA bei phaseDetail
  ausgeblendet, „…"-Fallback, keine Queue-Anzeige).
