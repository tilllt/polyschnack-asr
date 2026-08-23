# Change 099 — Settings aus dem Recording entfernen: Runs sind die einzige Wahrheit

**Status:** Proposal (vor Umsetzung)
**Anlass:** User 23.08. („Ja weiter" auf Etappe-2-Angebot): Die
`enable_*`-Spalten sind als Read-Mirror deklariert (Change 094, models.py),
aber die Laufzeit liest sie noch aktiv — der Run-Snapshot ist bisher reine
Archiv-Kopie, nicht Quelle der Wahrheit.

## Ist-Zustand (Analyse 23.08.)
Settings-Spalten auf `Recording`: `backend`, `language`, `enable_vad`,
`enable_diarize`, `diarize_num_speakers`, `diarize_min_duration_off`,
`diarize_method`, `enable_streaming`, `enable_noise_reduce`, `enable_enhance`,
`enable_punctuation`, `enable_llm_enhance`, `llm_endpoint_id`,
`prompt_template_id` (+ `delivery_target_id`).

- **Schreiben:** Upload (recordings.py:829-836) + transcribe/retranscribe
  (Form-Body) → Recording-Spalten.
- **Lesen (aktiv):** process_recording (service.py:1396-1435),
  _schedule_realign (:1052-1059), _schedule_rediarize (:1113-1120, :1161-1163),
  ETA-Schätzung (recordings.py:549-554), export_backup.py:57-66,
  API-Serialisierung (recordings.py:634-641).
- `TranscriptionRun` snapshotet die Settings bei Job-Start (service.py:1427),
  fehlt aber `delivery_target_id`.

## Ziel
`Recording` = Stamm ohne Settings. Jeder Lauf (Upload-Plan, Transkription,
Re-Transkription, Re-Align, Re-Diarize) lebt als `TranscriptionRun` mit seinen
Settings. Die API liefert `enable_*`-Felder weiterhin (aus dem aktuellen Run)
→ Frontend bleibt unverändert kompatibel.

## Regeln
1. **Upload:** Form-Felder → neuer `queued`-Run (Settings), Recording ohne
   Settings. `current_run_id` zeigt auf ihn, solange er der jüngste ist.
2. **transcribe:** Existiert ein `queued`-Run → Settings aus ihm + Body-
   Overrides (Body-Felder sind Optionals); sonst neuer Run aus dem Body.
   `process_recording` verarbeitet DIESEN Run.
3. **retranscribe:** Immer neuer Run (Body-Settings).
4. **realign/rediarize:** Body-Optionen → neuer `queued`-Run (Settings =
   Kopie des current_run + Overrides) → Worker liest Settings aus dem Run.
5. **Leser (ETA, Backup, Serialisierung):** Settings aus dem aktuellen Run
   (current_run_id; Fallback: jüngster Run; sonst Defaults).
6. **Migration (Startup, idempotent):**
   a. Backfill: Recordings ohne Run → Baseline-Run (`done`) + Result
      (text/segments) aus den Altdaten — NUR solange die Spalten existieren.
   b. `ALTER TABLE recording DROP COLUMN` je Settings-Spalte (SQLite 3.35+),
      nur wenn die Spalte existiert UND das Modell sie nicht mehr hat.
7. **Frontend:** keine Änderung (Payload-Form bleibt).

## Offene Punkte vor Umsetzung
- `TranscriptionRun.delivery_target_id` ergänzen (fehlt im Snapshot).
- Bestehende Tests, die `rec.enable_*` setzen/lesen, auf Run umstellen.
- test_runs.py erweitern: queued-Run-Übernahme, Backfill, DROP-Idempotenz.
