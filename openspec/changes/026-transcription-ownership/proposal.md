# Change 026 — Ownership-Übertragung für Ground-Truth-Transkriptionen

## Problem

Der Ground-Truth-Workflow aus Change 025 (REQ-BENCH-027) setzt voraus, dass
**die Projektleitung** die Vortranskripte manuell korrigiert. Für 33 Walzen
(~76 min stark verrauschtes historisches Audio) ist das erheblicher
manueller Aufwand. Hermes kann die Transkriptionen selbst anfertigen
(korrigierte Referenz auf Basis der Modell-Hypothesen) — aber es fehlt ein
**verbindlicher Ownership-Mechanismus**:

- Wer besitzt eine vom Agenten gefertigte Transkription? Wie wird sie zur
  verbindlichen Ground Truth?
- Wie übergibt der Agent die Ownership an die Projektleitung, und wie
  nimmt sie diese an?
- Wo liegen „Agent-Dateien" und wo „User-Dateien"? Der Übergang muss
  sichtbar sein (physischer Wechsel des Ablageorts), nicht nur ein
  Metadaten-Flag.

Ohne klare Ownership-Regeln bestünde die Gefahr zirkulärer Benchmarks
(Agent-Modell misst gegen Agent-Referenz, ungeprüft) und es bliebe
undurchsichtig, welche Transkription wer verantwortet.

## Ziel

1. **Ownership-Zustände** je Transkription: `agent` (Entwurf) →
   `proposed` (zur Übertragung vorgelegt) → `user_owned` (angenommen).
2. **Übertragungsprotokoll:** Hermes fertigt Ground-Truth-Transkriptionen
   an, überträgt sie an die Projektleitung; die Projektleitung nimmt an
   (oder fordert Nachbesserung).
3. **Physische Verschiebung bei Annahme:** Angenommene Transkriptionen
   werden aus dem Agent-Bereich **in die User-Dateien verschoben**
   (Ablageort wechselt, Provenienz dokumentiert).
4. **Anti-Gaming:** Nur `user_owned`-Transkriptionen gelten als valide
   Ground Truth für Benchmark-Statistiken; Agent-Entwürfe sind
   ausdrücklich keine Referenz.

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- `benchmark/data/vintage_walzen/transcripts/` mit drei Ablagebereichen:
  `agent/` (Hermes-Entwürfe), `proposed/` (zur Annahme vorgelegt),
  `user/` (angenommen — „User-Dateien").
- `ownership.json`: Status-/Provenienz-Metadaten je Sample
  (`owned_by`, `status`, `transcribed_by`, `accepted_at`, …).
- CLI-Skript `benchmark/scripts/ownership.py`:
  `list` / `propose` / `accept` / `revise` / `reject`.
- `ground_truth.json` enthält nur noch angenommene
  (`user_owned`) Referenzen; Agent-Entwürfe fließen nicht in
  Kategorie-Mittelwerte.
- Die Projektleitung kann im Chat mit einer einfachen Bestätigung
  annehmen („annehmen" / „alle annehmen" / Sample-IDs); Hermes führt die
  Verschiebung aus.

## Abgrenzung / Ehrlichkeit

- Eine vom Agenten **gefertigte** Transkription ist keine unabhängige
  Referenz (anders als FQS-Tool-Transkripte). Sie wird im Report als
  „vom Agenten transkribiert, von der Projektleitung angenommen"
  ausgewiesen — erst die Annahme macht sie zur verbindlichen Ground Truth.
- Der Agent markiert schwierige Passagen (unverständlich, Tonhöhen-
  schwankungen) mit `confidence: niedrig`; diese Samples bleiben einzeln
  geführt und fließen nicht in Kategorie-Mittelwerte (Regel aus Change
  025 bleibt bestehen).
- „User-Dateien" sind im ersten Schritt der Ablagebereich `transcripts/user/`
  **im Benchmark-Repo** (Versionierung, Provenienz). Eine Anbindung an die
  PolySchnack-Webapp-Transkriptionsbibliothek (KI-Box) ist bewusst **out
  of scope** — das wäre ein eigener Change.
- Rechte: unverändert zu Change 025 (Wachston-Audio nicht außerhalb des
  Repos weitergeben).

## Specs-Delta

`MODIFIED` — `specs/engineering/spec.md`: REQ-BENCH-027 (Workflow um
Agent-Erstellung und Ownership erweitert)
`ADDED` — REQ-BENCH-029/030/031 (Ownership, Übertragung, Anti-Gaming)
