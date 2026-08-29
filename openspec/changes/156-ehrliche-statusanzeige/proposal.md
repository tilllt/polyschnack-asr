# Change 156 — Ehrliche Statusanzeige (keine Pseudo-Infos)

**Status:** Proposed

## Befunde (2026-08-29, live auf der Box beobachtet)

1. **Stale „Processing"-Badges:** 3 Recordings zeigen Spinner + „Processing",
   obwohl KEIN Job läuft — `rec.status` blieb nach dem Stack-Restart auf
   `processing` (kein Reconcile mit der Job-Tabelle).
2. **Laufender Job unsichtbar:** Recording 297 lief im Align (Job-Tabelle:
   `kind=align, status=running`), die Karte zeigte aber „ready" — die UI
   mappt nur `rec.status` (Transkription), nicht den aktiven Job.
3. **Queue-Zeile zeigt falschen Prozess:** „297 ps-pk-onnx Processing" — das
   Backend des ERSTEN Jobs (transcribe), obwohl längst die Diarization
   (crispr-diar) lief. `GET /api/queue` liefert weder `kind` (Phase) noch
   Fortschritt.
4. **Kein echter Fortschritt bei /progress-404:** deployter crispr-diar hatte
   den Endpoint noch nicht (Fix kommt mit v0.8.30 — Change 155-Batch).
5. **Align/Sep liefern serverseitig keinen Fortschritt** (`g_server_progress`
   wird nur im transcribe-Handler aktualisiert, PR #408) — hier ehrlich
   „kein Fortschritt verfügbar" statt Fake-Prozent.

## Lösung: Status aus der Job-Tabelle ableiten

### Backend
1. **Reconcile** (`app/service.py` oder Start/Periodik): Recordings mit
   `status in (queued, processing)` und KEINEM aktiven Job (jobs-Tabelle)
   → korrigieren: Transkription vorhanden → `done`, sonst `failed`.
2. **Recording-API:** bei aktiven Jobs (transcribe/diarize/align/sep)
   meldet die Recording: `status=processing` + `phase` (kind) +
   `phase_label` (de) + `progress_pct` (echt, sonst null) +
   `progress_note`. Kein aktiver Job → `status` aus `rec.status`
   (reconciled).
3. **Queue-API (`GET /api/queue`):** pro Job `kind` + `progress_pct` +
   `progress_note` + `backend` — die Anzeige zeigt Phase statt Job-ID.

### Frontend
4. **RecordingCard:** Spinner/Badge NUR bei echtem aktiven Job; Anzeige
   „Diarization läuft — 42 %" / „Alignment läuft (meldet keinen
   Fortschritt)".
5. **Queue-Dialog:** Zeile mit Phase + Backend-Label + Fortschritt statt
   „297 ps-pk-onnx Processing".

## Akzeptanzkriterien
- [ ] Kein Spinner/Badge ohne laufenden Job (auch nach Restart)
- [ ] Laufende Diarization/Alignment erscheint auf der Karte als Phase
- [ ] Queue-Zeile zeigt Phase + echten Fortschritt (oder „kein Fortschritt verfügbar")
- [ ] Backend-Tests: Reconcile + Job-Kontext
