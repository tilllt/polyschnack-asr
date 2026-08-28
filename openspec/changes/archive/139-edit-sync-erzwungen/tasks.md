# Change 139 — Tasks (Edit-Sync erzwungen)

## 1. Frontend

- [x] `resegment.ts`: `rebuildWordsFromText` (pure, gleichverteilt)
- [x] `SegmentList.handleSave` (Solo): sofortiges `onEdited(next, text,
      manual=true)` + Words-Neubau + voller Listen-PUT
      (`replaceSegments(rid, next, false)`) + Rollback/Toast im Fehlerfall;
      `resolveServerTarget` entfernt
- [x] `onEdited`-Prop-Typ um `manual?: boolean` erweitert
- [x] i18n `edit_save_error` (de/en/pt-BR)

## 2. Tests

- [x] editindex.test.tsx: PUT-Liste statt PATCH, sofortiges onEdited mit
      Edit-Inhalt, createVersion=false
- [x] annotate.test.tsx: Anzeige zeigt den neuen Text nach Edit-Save
      (Wort-Spans aus neu gebauten Words)
- [x] Vitest gesamt 377 passed, tsc clean, build OK

## 3. OpenSpec

- [x] proposal/design/tasks (139), CLI-Validierung
- [ ] Spec-Delta auf `transcription-view` (Req 7) anwenden
- [ ] Nach Umsetzung archivieren

## 4. Commit, Push, CI

- [ ] Commit(s), Push direkt auf main, CI-Watch bis success, melden
