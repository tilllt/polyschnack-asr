# Change 026 — Design

## Ownership-Zustandsmaschine

```
┌──────────┐  propose   ┌──────────┐   accept    ┌────────────┐
│  agent   │──────────▶ │ proposed │───────────▶ │ user_owned │
└──────────┘            └──────────┘             └────────────┘
     ▲                      │   │
     │      revise          │   │ reject
     └──────────────────────┘   └──────────────▶ (agent, Status rejected;
                                                   wird in Ownership-Log
                                                   dokumentiert, Text bleibt
                                                   in agent/ als Historie)
```

- **agent** (`owned_by: agent`, `status: draft`): Hermes-gefertigter
  Entwurf im Agent-Bereich `transcripts/agent/`. Keine Benchmark-Wirkung.
- **proposed** (`status: proposed`): zur Übertragung vorgelegt, liegt in
  `transcripts/proposed/`; Hermes wartet auf Annahme oder Nachbesserung.
- **user_owned** (`status: accepted`): von der Projektleitung angenommen;
  Datei wurde nach `transcripts/user/` **verschoben**. Einziger
  Status, der als valide Ground Truth zählt.

## Ablage (Benchmark-Repo)

```
benchmark/data/vintage_walzen/
├── audio/                      # 33 MP3 (unverändert)
├── hypotheses_whisper.json     # Vortranskriptionen (Modell-Ausgabe)
├── hypotheses_parakeet.json    # Vortranskriptionen (A/B-Test)
├── transcripts/
│   ├── agent/     <sample>.txt # Hermes-Entwürfe (owned_by=agent)
│   ├── proposed/  <sample>.txt # zur Annahme vorgelegt (status=proposed)
│   └── user/      <sample>.txt # angenommen (owned_by=user) — User-Dateien
├── ownership.json              # Status-/Provenienz-Metadaten je Sample
└── ground_truth.json           # konsolidierte Referenz: NUR user_owned
```

`ownership.json` je Sample (Schema):

```json
{
  "Beim-Zahnarzt": {
    "owned_by": "user",
    "status": "accepted",
    "transcribed_by": "agent",
    "corrected_by": "agent",
    "confidence": "hoch",
    "source": "vintage_walzen",
    "language": "de",
    "proposed_at": "2026-08-19T…",
    "accepted_at": "2026-08-19T…",
    "accepted_by": "tilllt",
    "accepted_via": "matrix"
  }
}
```

## CLI-Skript `benchmark/scripts/ownership.py`

- `list [--status draft|proposed|accepted]` — Status aller Samples.
- `propose [--ids …]` (Default: alle `agent`-Entwürfe) — Textdateien nach
  `transcripts/proposed/` verschieben, `status=proposed`, `proposed_at`
  setzen; Übergabe-Manifest `transcripts/proposed_manifest.json`
  (Sample-ID, Datei, Wortzahl, confidence) erzeugen.
- `accept --ids …|--all` — Verschiebung `proposed/ → user/`,
  `status=accepted`, `owned_by=user`, `accepted_at/by/via` setzen;
  `ground_truth.json` aus den `user/`-Dateien regenerieren.
- `revise --ids …` — zurück nach `agent/` (Nachbesserung durch Hermes).
- `reject --ids …` — zurück nach `agent/` mit Status-Historie (rejected),
  Text verbleibt als Historie, wird nicht erneut vorgeschlagen.

Alle Aktionen idempotent, mit `--dry-run`. Tests: `tests/test_ownership.py`
(Zustandsübergänge, Verschiebungen, GT-Regenerierung).

## Workflow (Ablauf)

1. **A/B-Entscheidung** (Change 025-Zwischenschritt): Whisper vs. Parakeet
   auf 3 Beispiel-Walzen; Gewinner wird Vortranskriptions-Basis.
2. **Agent erstellt GT-Entwürfe:** Hermes überarbeitet die
   Vortranskriptionen der 33 Walzen zu korrigierten Referenzen
   (`transcripts/agent/`), je Sample mit `confidence`. Unverständliche
   Passagen: `confidence: niedrig` (keine Mittelwert-Wirkung).
3. **Propose:** Hermes legt die Entwürfe zur Übertragung vor
   (`ownership.py propose`), Übergabe-Manifest + kurze Liste im Chat.
4. **Annahme:** Projektleitung bestätigt im Chat („annehmen",
   „alle annehmen" oder Sample-IDs). Hermes führt `ownership.py accept`
   aus → Dateien **wandern nach `transcripts/user/`**, GT wird
   konsolidiert, Commit + Push.
5. **Nachbesserung:** Bei Einwänden (`revise`/`reject`) überarbeitet
   Hermes den Entwurf und schlägt erneut vor.

## Integration

- `prepare.py`: Kategorie `vintage_walzen` liest `ground_truth.json`
  (generiert aus `user/`). Samples ohne angenommene GT werden nicht ins
  Manifest aufgenommen (keine Degradation, kein Dummy-Text).
- `report.py`: GT-Quelle als „vom Agenten transkribiert, von der
  Projektleitung angenommen" ausweisen; `confidence: niedrig`-Samples
  nur einzeln (bestehende Regel).
- `docs/component-decisions.md`: Ownership-Eintrag nach Abschluss.

## Offene Frage

- **Zielablage „User-Dateien":** Default ist `transcripts/user/` im
  Benchmark-Repo (versioniert, nachvollziehbar). Falls die Projektleitung
  eine Ablage außerhalb des Repos wünscht (z. B. eigener Transkriptions-
  Ordner oder PolySchnack-Webapp), wird der Zielpfad über eine
  Konfiguration (`ownership.user_dir`) gesetzt; die Provenienz- und
  Status-Logik bleibt identisch.
