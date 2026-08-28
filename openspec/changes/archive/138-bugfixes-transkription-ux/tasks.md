# Change 138 — Tasks (Bugfix-Runde)

## 1. Backend: Speaker-Rename tolerant

- [ ] `segments.py`: `_speaker_key(s) -> int | None` (strikte Nummern-
      Extraktion, s. design.md) + `rename_speaker` vergleicht Keys
      (`_speaker_key(s.get("speaker")) == _speaker_key(from_speaker)`),
      ersetzt mit `to_speaker`; `renamed`-Count ehrlich; 400 nur wenn
      nichts matcht
- [ ] Tests `test_speaker_rename.py` erweitern: `SPEAKER_01`↔`SPEAKER_1`↔
      `01`↔`1`↔`speaker_1`-Dreh, Buchstabe `A`, kein Match ohne Nummer/
      leerem speaker, `renamed`-Count, 400-Fall, Roundtrip SRT/Export
      konsistent (Speaker-Feld ersetzt)

## 2. Frontend: Punctuation-Option backend-bewusst

- [ ] `RecordingCard.tsx`: `nativePunctuationByBackend` aus der Matrix
      (Muster `streamingByBackend`) + Prop `nativePunctuation` ans
      OptionsPanel (für das gewählte Backend)
- [ ] `OptionsPanel.tsx` (+ `FeatureToggles.tsx` falls dort gerendert):
      bei `nativePunctuation` Toggle disabled + gesetzt + „(nativ)"-Hinweis
      + Erklärtext; sonst unverändert
- [ ] i18n-Keys de/en/pt-BR (z. B. `punct_native_hint`)

## 3. Frontend: Detail-Poll bei queued

- [ ] `hooks.ts`: pure Helfer `detailEnabled(status)` /
      `shouldPollDetail(status)` exportieren; `useRecordingDetail` nutzt sie
      (enabled: done|processing|queued; Intervall: processing|queued → 2000)
- [ ] Tests `hooks.test.ts`: Helfer-Matrix (uploaded/queued/processing/done/
      failed)

## 4. Suites + Build

- [ ] Backend: `pytest tests/test_speaker_rename.py` + volle Suite
- [ ] Frontend: Vitest (neue Tests) + `tsc --noEmit` + `npm run build`

## 5. OpenSpec

- [ ] Spec-Deltas schreiben (`changes/138/specs/…`), CLI-validieren
- [ ] Nach Umsetzung: auf `openspec/specs/` anwenden + archivieren

## 6. Commit, Push, CI

- [ ] Commit(s), Push direkt auf main, CI-Watch bis success, melden
