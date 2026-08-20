# Change 057 — Tasks

## Phase 1: Backend
- [x] `models.py`: Feld `diar_status` (done|pending|running|failed,
      Default done) am Recording, analog `alignment`
- [x] `routers/segments.py` (wie Re-Align): `POST /recordings/{rid}/rediarize`
      (write-Zugriff, Voraussetzungen status=done + Audio + Diar-Dienst
      erreichbar; 409/503 mit klarer Meldung)
- [x] Worker (Muster `_schedule_realign`): Diarization auf dem Audio via
      bestehendem Diar-Dienst (`diarize_method` des Recordings), Sprecher-
      Intervalle → `speaker` je Segment (Wort-Überlappung, gleiche Logik
      wie die Pipeline `_build_word_stream` + `_merge_diarization`);
      Text/Wörter/Zeiten/alignment unverändert; `diar_status`-Updates +
      ehrliche `progress_note` („Re-Diarize läuft …“, kein Fake-Progress);
      `updated_at` setzen; Versions-Guard (fremde Edits → skipped)
- [x] Backend-Tests: Endpunkt-Rechte (write), Voraussetzungs-Fehler
      (409/503), Worker setzt speaker korrekt (Intervall-Mapping),
      Text/alignment unverändert, Status-Übergänge, diar down → failed

## Phase 2: Frontend
- [x] `api.ts`: `rediarizeRecording(id)` + `diar_status`/`diar_running` im
      Recording-Typ
- [x] RecordingCard: Button „Re-Diarize" neben Re-Transcribe/Re-Align
      (nur status=done + write), disabled während running, ehrlicher Status
      („Diarize läuft…"), Fehler als Toast (kein stiller Fail)
- [x] i18n de/en/pt-BR (rediarize, rediarize_running, rediarize_error…)

## Phase 3: Qualität
- [x] tsc --noEmit sauber, vitest + Backend-Suite grün
- [ ] OpenSpec-Proposal abgleichen, Commit + Push, CI prüfen und melden
