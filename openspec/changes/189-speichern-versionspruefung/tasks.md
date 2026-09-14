# Tasks — Change 189

- [x] Backend: `expected_updated_at` im PUT-Body (`segments.py`), Vergleich,
      409-Antwort (+ Header `X-Current-Updated-At`), Log-Warnung ohne Feld
- [x] Backend: Test „stale write wird abgelehnt, keine Version, Text bleibt"
      (`tests/test_stale_write.py`)
- [x] Backend: Test „passender Zeitstempel schreibt normal"
- [x] Backend: Test „ohne Feld schreibt wie bisher (Kompatibilität)"
- [x] Frontend: `api.ts` — `replaceSegments(..., expectedUpdatedAt)`,
      `isStaleWriteError`, Status + Serverstand am Fehlerobjekt
- [x] Frontend: 409-Behandlung in `SegmentList` (kein Rollback der Eingabe, kein
      Auto-Retry), Banner + „Neu laden" in `RecordingCard`, i18n
      (`stale_write_error`, `stale_write_reload` in DE/EN/PT)
- [x] Yjs: Raumname mit `updated_at`-Suffix (`useYjsTranscription(..., roomStamp)`),
      `SegmentList` übergibt den geladenen Stand
- [ ] Doku: Betriebsregel „serverseitige Reparaturen nur bei geschlossener
      Sitzung" (admin.md + Kollaborations-Doku)
- [ ] Verifikation in Prod: laden, serverseitig schreiben, im UI speichern →
      409 statt stillem Überschreiben; danach Re-Align der Wortzeiten
