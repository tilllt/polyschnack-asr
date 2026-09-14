# Tasks — Change 189

- [ ] Backend: `expected_updated_at` im PUT-Body (`segments.py`), Vergleich,
      409-Antwort, Log-Warnung ohne Feld
- [ ] Backend: Test „stale write wird abgelehnt, keine Version, Text bleibt"
- [ ] Backend: Test „passender Zeitstempel schreibt normal"
- [ ] Backend: Test „ohne Feld schreibt wie bisher (Kompatibilität)"
- [ ] Frontend: `api.ts` — `replaceSegments(..., expectedUpdatedAt)`; Aufrufer
      übergeben den geladenen Stand
- [ ] Frontend: 409-Behandlung (Banner + „Neu laden"), kein Auto-Retry;
      Test dazu
- [ ] Yjs: Raumname mit `updated_at`-Suffix; Client betritt den Raum mit dem
      geladenen Stand; Test/Prüfung, dass alter Text nicht mehr überlagert
- [ ] Doku: Betriebsregel „serverseitige Reparaturen nur bei geschlossener
      Sitzung" (admin.md + Doku zur Kollaboration)
- [ ] Verifikation am Prod-Fall 328: laden, serverseitig schreiben, im UI
      speichern → 409 statt stillem Überschreiben
