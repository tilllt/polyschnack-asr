# Tasks — Change 123 (Self-Healing: Einträge ohne uid + retranscribe-Härtung)

## Done

- [x] Proposal: openspec/changes/123-self-healing-missing-uid/proposal.md
- [x] Rot-Test: retranscribe ohne Datei gab 200/still enqueue (kein 410)
- [x] Fix: _repair_missing_uids in db.py (recording + annotation, uid
      NULL/leer → hex-uid), Aufruf in init_db
- [x] Fix: _ensure_audio_present in retranscribe → 410 (konsistent mit
      transcribe/duplicate)
- [x] tests/test_missing_uid_repair.py: 4/4 grün (Repair recording +
      annotation, retranscribe 410, delete ohne Datei geht)
- [x] Nachbar-Suiten: boot_recovery, delete, duplicate, realign 17/17 grün
- [x] Live: Waise mit uid='' → Repair → 32-hex-uid; DELETE per API →
      403 (Zugriff) statt 404 (nicht gefunden) = adressierbar

## Verifikation

- [ ] Backend-Gesamtsuite grün (läuft)
- [ ] Push main → CI success
- [ ] Prod-Deploy durch User → Waisen-Einträge löschbar/retranskribierbar
      (Retranscribe ohne Datei zeigt jetzt 410 statt stillem Enqueue)
