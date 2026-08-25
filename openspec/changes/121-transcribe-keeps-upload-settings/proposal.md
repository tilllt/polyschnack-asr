# Change 121 — transcribe überschreibt Upload-Settings nicht mehr still

## Problem

`POST /api/recordings/{rid}/transcribe` überschreibt die Settings des
queued-Runs BEDINGUNGSLOS mit seinen Form-Defaults (`enable_vad=False`,
`vad_mode="off"`, `enable_diarize=False`, `enable_noise_reduce=True`, …).

- Change 099-Intention: „Existiert ein queued-Run (vom Upload), werden
  DESSEN Settings aktualisiert" — gemeint war: übernehmen.
- Tatsächlich: Ein Client, der nach dem Upload `transcribe` OHNE die
  Settings-Felder aufruft (curl, externe Integrationen), verliert still
  seine Upload-Auswahl — VAD/Diarize laufen dann de facto nicht, ohne
  dass irgendetwas das meldet.
- Live belegt (Dev-Instanz): Upload mit `enable_vad=true` +
  `enable_diarize=true` → Run speichert `edges/1` → `transcribe` ohne
  Parameter → Run still auf `off/0` zurückgesetzt.
- Das Frontend (`startTranscription`) sendet alle Felder immer mit —
  der Browser-Flow ist unbetroffen, der Fix darf ihn nicht ändern.

## Lösung

Die Parameter werden `Optional` mit `None`-Default: Fehlt das Feld im
Request, bleibt der bestehende Run-Wert erhalten (nur explizit gesendete
Felder überschreiben). Existiert KEIN queued-Run, gelten die bisherigen
Modell-Defaults für den neu angelegten Run.

- Browser-Flow: sendet alle Felder → identisches Verhalten.
- Externe Clients: Upload-Settings überleben den Transcribe-Call.
- `enable_punctuation`/`enable_llm_enhance` sind bereits `Optional` —
  Muster übernehmen.

## Tests (TDD)

1. Neu `tests/test_transcribe_keeps_upload_settings.py`:
   Upload mit `enable_vad=true`, `enable_diarize=true` → `transcribe`
   ohne Form-Felder → Run behält `vad_mode=edges`, `enable_diarize=1`.
   (Vorher rot: Run wird auf `off/0` überschrieben.)
2. Gegenprobe: `transcribe` MIT `enable_vad=false` explizit → Run wird
   auf `off` gesetzt (explizite Übergabe gewinnt weiterhin).
3. Kein queued-Run (z.B. direkt angelegtes Recording) → neuer Run mit
   Modell-Defaults (`off/False`, `enable_noise_reduce=True`).

## Verifikation

- [ ] Rot-Test belegt den stillen Fail
- [ ] Fix in `app/routers/recordings.py` (transcribe_ep)
- [ ] `pytest tests/test_transcribe_keeps_upload_settings.py` grün
- [ ] Komplette Backend-Suite `pytest tests/` grün (974 + neue)
- [ ] Frontend-Suite unberührt (kein Frontend-Code geändert)
- [ ] Live: Upload mit VAD → transcribe ohne Parameter → Run behält VAD
- [ ] Push main → CI success
