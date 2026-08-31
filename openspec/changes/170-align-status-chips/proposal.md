# Change 170 — UI-Status für align/rediarize-Jobs (Phase + Startzeit)

**Status:** Proposed

## Befund (2026-08-31, Live: „New word timestamps" → process)

Beim Start eines align- („New word timestamps") oder rediarize-Jobs zeigte
die UI: alle Phasen-Chips (preparing/transcribing/aligning…) sichtbar und
die **blinkende Kachel „finalizing · läuft seit 180m"** — obwohl der Job
gerade erst startete und eigentlich align/diarize lief.

Ursache: Die Hintergrund-Jobs setzen nur `rec.alignment = "running"`
bzw. `rec.diar_status = "running"` — aber **nicht** `progress_note` mit
Phasen-Key und **nicht** `phase_started_at`. Die Chips
(`activePhaseIndex`) fielen auf den pct-Fallback des ALTEN
Transcribe-Laufs (pct ≥ 95 → „finalizing" blinkt) und die
Zeit-Anzeigen (sincePhase/sinceStart, ETA-Basis) rechneten mit den
Stunden alten Start-Zeiten („läuft seit 180m").

## Lösung

Beide Job-Starter setzen beim Statuswechsel auf „running" zusätzlich
`crud.set_progress(rec_id, 1, "<phasen-key>")` — diese Funktion setzt
pct + `last_heartbeat_at` + bei Notenwechsel `phase_started_at`:
- align (`_run_background_align`): Note `"alignment"` → Chip „aligning"
- rediarize (`run_rediarize_job`): Note `"diarization"` (ersetzt die
  unbrauchbare Text-Note „Re-Diarize läuft …") → Chip „diarizing"

`activePhaseIndex` kennt beide Keys bereits (Frontend unverändert); die
Align-/Diar-ETA rechnet ab jetzt ab Job-Start (`phase_started_at`).

## Tests

- Backend: `set_progress` setzt bei Notenwechsel `phase_started_at`
  (bestehender crud-Test, falls vorhanden, bleibt grün).
- Manuell (Box): „New word timestamps" starten → Chip „aligning" blinkt,
  „läuft seit <Sekunden>", keine 180m-Altlast.
