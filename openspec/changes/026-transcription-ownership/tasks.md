# Change 026 — Tasks

## Phase 1: Mechanik
- [ ] `benchmark/scripts/ownership.py` implementieren
      (list/propose/accept/revise/reject, idempotent, `--dry-run`)
- [ ] `tests/test_ownership.py` (Zustandsübergänge, Verschiebungen,
      GT-Regenerierung, rejected-Historie)
- [ ] `prepare.py`: `vintage_walzen`-GT aus `ground_truth.json` lesen;
      Samples ohne angenommene GT nicht ins Manifest
- [ ] Report: GT-Quelle („vom Agenten transkribiert, von der
      Projektleitung angenommen") ausweisen

## Phase 2: Ground Truth durch Hermes
- [ ] A/B-Test Whisper vs. Parakeet auf 3 Beispiel-Walzen abschließen;
      Entscheidung dokumentieren (component-decisions.md)
- [ ] Vortranskription aller 33 Walzen mit dem Gewinnermodell
- [ ] Hermes erstellt GT-Entwürfe (`transcripts/agent/`), je Sample
      mit `confidence`; unverständliche Passagen → `niedrig`

## Phase 3: Übertragung
- [ ] `ownership.py propose` → Übergabe-Manifest + Liste im Chat
- [ ] Annahme durch Projektleitung („annehmen" im Chat)
- [ ] `ownership.py accept` → Verschiebung nach `transcripts/user/`,
      `ground_truth.json` regenerieren
- [ ] Commit + Push (benchmark-Repo + pk-asr), CI prüfen und melden

## Phase 4: Messung + Doku
- [ ] Backend-Messung aller Backends (`--categories vintage_walzen`)
      auf frischer vast-Instanz je Backend
- [ ] `docs/component-decisions.md`: Eintrag „Robustheit auf
      historischem Material" + Ownership-Vermerk
- [ ] Businessplan 3.4 ergänzen (echte Vintage-Werte, Hinweis auf
      Agenten-Transkription + Annahme durch Projektleitung)
