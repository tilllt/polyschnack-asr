# Change 069 — Pending-Uploads: 500-Fix + Datei-Info + Discard

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User-Befund (2026-08-21, mobile): Eine versehentliche, sehr kurze
Aufnahme landete im lokalen Puffer („recording saved locally upload
pending"). Beim Retry kam **Error 500**, und die Aufnahme konnte weder
„discardet" noch identifiziert werden (kein Dateiname, keine Größe).

Root Cause (lokal reproduziert, `test_short_upload.py`): sehr kurze /
kaputte Recorder-Blobs (z. B. 12 Bytes) lassen `prepare_storage` →
`convert_to_mp3` einen `RuntimeError` werfen; der wurde nicht in einen
HTTP-Fehler übersetzt → **500** statt verständlicher Meldung.

## Ziel

1. **Kein 500**: Konvertier-Fehler → **422** mit klarer Meldung („Audio
   konnte nicht gelesen werden (Datei zu kurz oder beschädigt) …").
2. **Datei-Info im Pending-Banner**: Dateiname, Größe, Aufnahmezeit je
   Eintrag — der User sieht, was im Puffer liegt.
3. **Discard pro Eintrag**: lokale Aufnahme verwerfbar (✕ Discard) —
   ohne Retry-Schleife.
4. **Fehler-Detail beim Retry**: der Server-`detail` (z. B. die 422-
   Meldung) wird im Toast angezeigt statt nur „HTTP 500".

## Verhaltens-Delta (IST → SOLL)

- **IST:** kaputte/kurze Aufnahme → Retry 500; Banner zeigt nur „N
  pending"; kein Discard; kein Datei-Info.
- **SOLL:** kaputte Aufnahme → 422 mit Meldung; Banner listet
  Dateiname/Größe/Zeit; Discard möglich; Retry-Toast zeigt die Ursache.

## Umsetzung

1. `app/routers/recordings.py::upload_recording`: `prepare_storage` in
   try/except RuntimeError → HTTPException(422, deutsche Meldung).
2. `UploadZone.tsx`: pendingRecs-State (Dateiname/Größe/createdAt),
   Liste im Banner, ✕ Discard (deletePendingRecording), Retry-Toast mit
   Server-Detail.
3. Tests: `test_short_upload.py` (4): 0,1 s WAV → 201; 0,01 s → 201;
   Header-only WAV → 201/400/422; 12-Byte-Müll → **422 mit Meldung**.

## Referenzen

- Befund + Root Cause: reproduziert in `test_short_upload.py`
- `app/audio_utils.py::convert_to_mp3` (RuntimeError-Quelle),
  `frontend/src/offlineQueue.ts` (IndexedDB-Puffer)
