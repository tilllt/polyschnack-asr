# Tasks — Change 048: Boot-Recovery für hängende Hintergrund-Alignments

## Task 1: Recovery-Funktion

- [x] `recover_stale_alignments(session)` in service.py: Recordings mit
      `alignment IN ("pending","running")` → `skipped` + `.align-cache`-
      Dateien der betroffenen Recordings löschen
- [x] Idempotent, loggt Anzahl

## Task 2: Lifespan-Einbindung

- [x] Aufruf in main.py Lifespan nach `init_db()`, VOR dem Queue-Start

## Task 3: Tests

- [x] pending → skipped + Cache gelöscht (test_boot_recovery.py)
- [x] running → skipped
- [x] done/skipped bleibt unverändert; done-Cache bleibt liegen
- [x] Idempotenz (zweiter Lauf: 0)
- [x] 5/5 grün

## Task 4: Commit

- [ ] Backend-Gesamtsuite grün (läuft)
- [ ] Commit + Push + CI prüfen
