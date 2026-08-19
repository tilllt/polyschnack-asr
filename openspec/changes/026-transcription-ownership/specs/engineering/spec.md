# Engineering Spec — Delta für Change 026

## MODIFIED Requirements

### REQ-BENCH-027: Ground-Truth-Workflow für Quellen ohne Transkript
`Benchmark-Datensatz` · `must`

Der Workflow wird um die **Agenten-Erstellung mit Ownership-Übertragung**
erweitert. Zusätzlich zur manuellen Korrektur durch die Projektleitung
gilt:

1. Hermes kann Ground-Truth-Transkriptionen **anfertigen**
   (korrigierte Referenz auf Basis dokumentierter Vortranskriptionen)
   und legt sie in `transcripts/agent/` ab (owned_by=agent, status=draft).
2. Die Übertragung an die Projektleitung erfolgt über den Status
   `proposed` (Datei in `transcripts/proposed/`, `proposed_at` gesetzt,
   Übergabe-Manifest).
3. **Erst die Annahme** durch die Projektleitung macht die Transkription
   zur verbindlichen Ground Truth: Status `accepted`, Datei wird nach
   `transcripts/user/` verschoben (`accepted_at`, `accepted_by`,
   `accepted_via` dokumentiert).
4. Provenienz je Sample bleibt Pflicht: `reference`, `source`,
   `language`, `confidence`, `transcribed_by`, `corrected_by`, `owned_by`.

## ADDED Requirements

### REQ-BENCH-029: Ownership-Zustände und Ablagebereiche
`Benchmark-Datensatz` · `must`

Jede Ground-Truth-Transkription hat genau einen Ownership-Zustand aus
{agent, proposed, user_owned} und liegt im zugehörigen Ablagebereich
`transcripts/{agent,proposed,user}/`. Zustandswechsel erfolgen
ausschließlich über `benchmark/scripts/ownership.py` (list, propose,
accept, revise, reject; idempotent, `--dry-run` unterstützt).
`ownership.json` dokumentiert Status und Provenienz je Sample.

### REQ-BENCH-030: Übertragung und Annahme mit physischer Verschiebung
`Benchmark-Datensatz` · `must`

- `propose`: verschiebt Entwürfe von `agent/` nach `proposed/` und
  erzeugt ein Übergabe-Manifest.
- `accept`: verschiebt die Textdateien von `proposed/` nach `user/`
  („in die User-Dateien"), setzt `status=accepted`, `owned_by=user` und
  die Annahme-Metadaten, und regeneriert `ground_truth.json` aus dem
  `user/`-Bereich.
- `revise`/`reject`: führen Entwürfe nach `agent/` zurück; `reject`
  dokumentiert die Ablehnung als Historie, der Text verbleibt als
  Historie und wird nicht erneut vorgeschlagen.

### REQ-BENCH-031: Anti-Gaming — nur angenommene Referenzen zählen
`Benchmark-Auswertung` · `must`

- Nur `user_owned`-Transkriptionen (Status `accepted`) fließen als
  Ground Truth in Benchmark-Statistiken und Kategorie-Mittelwerte ein.
- Agent-Entwürfe (`agent`) und vorgeschlagene Entwürfe (`proposed`)
  sind ausdrücklich **keine** valide Referenz; `prepare.py` nimmt
  Samples ohne angenommene GT nicht ins Manifest auf.
- Samples mit `confidence: niedrig` bleiben einzeln geführt und fließen
  nicht in Kategorie-Mittelwerte (Regel aus REQ-BENCH-027 unverändert).
- Der Report weist die GT-Herkunft aus: „vom Agenten transkribiert,
  von der Projektleitung angenommen".
