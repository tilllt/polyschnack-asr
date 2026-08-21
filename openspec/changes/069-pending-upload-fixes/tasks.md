# Change 069 — Tasks

## 1. Backend (500-Fix)

- [x] `upload_recording`: prepare_storage-RuntimeError → 422 mit Meldung
- [x] `test_short_upload.py`: 4 Tests (kurz WAV ok, 12-Byte-Müll → 422) — grün

## 2. Frontend Pending-Banner

- [x] pendingRecs-State (Dateiname/Größe/createdAt) + refreshPending lädt Liste
- [x] Banner: Liste je Eintrag (Name, Größe, Zeit) + ✕ Discard
      (deletePendingRecording)
- [x] Retry-Toast: Server-detail durchreichen (422-Meldung statt „HTTP 500"),
      Dateiname im Toast

## 3. Abschluss

- [ ] tsc + Frontend-Tests grün
- [ ] Vollsuite fail=0
- [ ] Commit + Push + CI
