# Change 123 — Self-Healing: Einträge ohne uid + retranscribe-Härtung

## Problem

User-Report (2026-08-25): „Es gibt immer noch Einträge die weder Soundfile,
Transkription o.ä. haben. Man kann sie nicht retranskribieren noch löschen
(404)."

- Die Liste serialisiert `uid` direkt aus der DB-Spalte. Einträge mit
  `uid IS NULL`/leer (Migrations-Altlast oder Crash-Waise) erscheinen in
  der Liste mit `uid: null` — das Frontend ruft dann
  `/api/recordings/null/retranscribe` bzw. `/delete` → `get_recording_by_uid`
  findet nichts → **404**. Der Eintrag ist unaufräumbar.
- Zusätzlich: `retranscribe` prüft die Audiodatei NICHT (anders als
  `transcribe`/`duplicate` mit `_ensure_audio_present`) — ein
  Re-Transcribe auf einer Aufnahme ohne Datei wird still enqueued und
  failt später ohne verwertbare Meldung (stiller Fail).

## Lösung

1. **Startup-Repair** in `init_db` (`_repair_missing_uids`):
   `UPDATE recording SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL
   OR uid = ''` — analog für `transcriptionrun`. Alt-Einträge bekommen
   damit gültige, eindeutige uids → Delete/Retranscribe/Detail funktionieren
   wieder, einmalig beim nächsten Start (danach greift der unique-Index).
2. **retranscribe-Härtung:** `_ensure_audio_present(rec)` direkt nach dem
   Zugriffs-Check → **410 mit klarer Meldung** statt stillem
   Enqueue-in-Failed (konsistent mit transcribe/duplicate).
3. **Delete bleibt ohne Datei-Check** — Waisen müssen immer aufräumbar sein.

## Tests (TDD)

1. `tests/test_missing_uid_repair.py`:
   - Zeile mit `uid=NULL` (per SQL, damit default_factory nicht greift) →
     Repair füllt eindeutige hex-uid (recording + transcriptionrun).
   - `retranscribe` auf Aufnahme ohne Datei → 410 (vorher 200/queued = rot).
   - `delete` auf Aufnahme ohne Datei → 200, Zeile gelöscht (muss gehen).

## Verifikation

- [ ] Rot-Test: retranscribe ohne Datei gibt vorher 200 (stiller Fail)
- [ ] Fix: Repair in init_db + _ensure_audio_present in retranscribe
- [ ] Neue Tests grün, Gesamtsuite grün
- [ ] Push main → CI success
- [ ] Prod-Deploy durch User → Waisen-Einträge sind löschbar/retranskribierbar
