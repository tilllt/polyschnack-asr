# Change 187 — Aufgaben (TDD, in dieser Reihenfolge)

Ziel-KPI an Recording 328 (`ae7435ca…`): Invarianten-Verletzungen 4/8 → 0,
Überlappung 14,52 s → 0, 414/414 Wörter echte Zeiten, 0 doppelte Wortzeiten,
zweiter Align-Lauf = `done (unverändert)`.

## 1. Reine Funktionen (Backend, ohne DB) — zuerst Tests

- [ ] `derive_bounds(segments)`: setzt `start`/`end` aus den Wörtern
      (`start = words[0].start`, `end = start des ersten Wortes des Folgesegments`,
      letztes Segment `words[-1].end`); Segmente ohne Wörter bleiben unberührt.
- [ ] `normalize_boundaries(segments)`: löst Überlappungen/Lücken nach der
      Schnitt-Regel auf (Pause → vorheriges Segment), ohne Wörter zu verändern.
- [ ] `assign_words_by_index(group_segments, aligned_words)`: Index-Zuordnung;
      Rückgabe `(segments, ok)` bzw. Fehlercode `word_count_mismatch`.
- [ ] `glue_group_boundary(prev_last_end, next_words)`: monoton verkleben.
- [ ] Tests: Tabellen-Tests + Fixtures aus dem Live-Fall (8 Segmente/414 Wörter,
      gedriftete Grenzen, 14,5-s-Überlappung). Erwartete Grenzen:
      0,24 · 12,00 · 41,93 · 55,67 · 73,64 · 109,20 · 138,20 · 157,48 · 170,59.

## 2. Choke-Point: Invariante zentral erzwingen

- [ ] `reconcile_words_to_text()` ruft am Ende `derive_bounds()` +
      `normalize_boundaries()` (alle Schreibpfade: ASR-Ergebnis, Align-Job,
      Edit-PUT, Migration).
- [ ] Tests: Text-Edit (gleiche/andere Wortzahl), Split, Insert, Drag ⇒
      Invariante gilt danach; Segment ohne Wörter bleibt unangetastet.

## 3. Align-Pfad: Fensterlogik raus

- [ ] `apply_aligned_words` durch `assign_words_by_index` ersetzen; Aufrufstelle
      in `_run_align_phase` anpassen (Gruppen-Offsets entfallen in der
      Merge-Liste — Zuordnung erfolgt gruppenweise über denselben Index).
- [ ] `build_align_groups` auf Wortbereiche/Segment-Schnitte umstellen
      (überlappungsfreie Gruppen) + `glue_group_boundary` an der Naht.
- [ ] Überschreibt **nur** Wörter und leitet danach Grenzen ab; kein
      `_distribute_words`-Fallback nach erfolgreichem Align.
- [ ] Tests: gedriftete Grenzen (alle 8 Segmente echte Zeiten), Wortzahl-Mismatch
      → `failed` + Grund, Naht-Fall 105,08/109,20 → keine Doppelzone.

## 4. Status- und Fehlersemantik

- [ ] Statusmatrix umsetzen (`done` / `done+unverändert` / `skipped` nur bei
      leerem Aligner-Ergebnis / `failed` mit Grund); Meldungstexte i18n (DE/EN).
- [ ] `separate_backend`-Nichterfüllung (409/down) als Job-Notiz + UI-Hinweis.
- [ ] Tests: „Aligner liefert, Ergebnis identisch" ⇒ `done (unverändert)` und
      **nicht** „Aligner lieferte keine Wort-Timestamps"; 409-Fall.

## 5. Frontend

- [ ] `ensureSegmentBounds()` um die Wortkanten-Invariante erweitern
      (Vorbeugung im Client, gleiche Regel wie Backend).
- [ ] Status-/Hinweistexte im UI (Align-Ergebnis, Music-Removal-Hinweis).
- [ ] Vitest: Drag/Split/Insert/`ensureSegmentBounds`; keine Regression.

## 6. Migration (explizite Admin-Aktion)

- [ ] Admin-Endpoint + Skript: `dry_run` (Bericht: Recording, Segmente mit
      Delta > 0,5 s, aufgelöste Überlappungen, Segmente ohne Wörter) und
      `apply` (schreibt abgeleitete Grenzen, Versions-Snapshot `kind="edit"`).
- [ ] Tests: Dry-Run verändert nichts; Apply zieht Grenzen, Wortzahl/Text bleiben;
      Segment ohne Wörter unangetastet.
- [ ] Ausführung auf Prod **nur nach User-Freigabe** — Recording 328 als erster
      Kandidat, Bericht vor dem Schreiben.

## 7. Doku & Verifikation

- [ ] Live-Spec `specs/transcription-view/spec.md` (Req 4/5/10) + ggf.
      `postprocessing` beim Archivieren anpassen.
- [ ] User-Doku: „Grenzen sitzen an den Wörtern — Re-Align zieht sie automatisch
      nach."
- [ ] Regression: Backend-Suite (1142+) und Frontend-Suite grün.
- [ ] Prod-Gegenprobe an Recording 328 (KPI oben) + Gegenprobe „normaler" Lauf
      (neue Transkription) ohne Regression.
