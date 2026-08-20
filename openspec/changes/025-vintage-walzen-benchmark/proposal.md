# Change 025 — Benchmark-Erweiterung: historische deutsche Aufnahmen (vintage_walzen + vintage_schellack)

## Problem

Die Benchmark-Kategorie „Vintage" (Schallplatte/Tonband/Film) besteht bislang
aus **TTS-Audio mit simulierten Degradationen** (Filter, Knistern, Rauschen).
Damit fehlt die Messung gegen **echtes historisches deutsches Audio** — genau
das Material, das Zielkunden (Archive, Medien, Forschung) verarbeiten wollen.
Zwei real verfügbare Quellen wurden identifiziert:

1. **Wachston-Phonographenwalzen** (wachston.de, privat, ~450 Walzen 1895–1925):
   33 **gesprochene deutsche** Aufnahmen (humoristische Szenen, Monologe,
   Couplets; Bendix/Schönwald/Sattler u. a., 1898–1914). Originale
   Walzenakustik: Bandbreite ~100 Hz–5 kHz, Knistern, Tonhöhenschwankungen.
   **Keine Transkripte online** — Ground Truth muss erstellt werden
   (Vortranskription + manuelle Korrektur durch Projektleitung,
   bereits zugesagt).
2. **vintage_schellack** (Internet Archive, 78rpm-Sammlung, **Public Domain,
   kein Login**): 14 gesprochene deutsche Aufnahmen 1902–1932 — Rezitationen
   (Josef Kainz „Hamlet"-Monolog 1902, Alexander Moissi Schiller 1912,
   Carl von Zeska 1907) und Couplets/Humor (Otto Reutter 1921, Ernest Balle
   Berliner Dialekt, Georg Barsch 1914, Saison-Couplet 1911, Fritzi Massary
   1932). Schellack-Akustik: Bandbreite ~200 Hz–6 kHz, Oberflächenrauschen.
   **Keine Transkripte online** — Ground Truth wie bei den Walzen.
   (Zwirner-Korpus/DGD wurde verworfen: User-Entscheidung 2026-08-20 —
   Zugang nur nach kostenloser Registrierung, kein offener API-Zugang.)

## Ziel

1. Echte historische deutsche Aufnahmen als Benchmark-Kategorien
   (`vintage_walzen` und `vintage_schellack`) in den PolySchnack-Benchmark
   aufnehmen.
2. Ground-Truth-Workflow für Quellen ohne Transkript etablieren:
   Vortranskription → Korrektur durch die Projektleitung →
   Review → `ground_truth.json` (dokumentiert, nachvollziehbar).
3. Alle eigenen Backends auf den neuen Kategorien messen (WER/RTF) und
   die Ergebnisse in Report, Decision-Log und Businessplan aufnehmen
   (Robustheit auf historischem Material).

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Der Benchmark enthält neue Subsets `vintage_walzen` (33 Samples,
  gesprochene Walzen 1898–1914) und `vintage_schellack` (14 Samples,
  Schellack 1902–1932).
- `benchmark/data/vintage_walzen/` mit `audio/`, `hypotheses_*.json`
  (Vortranskription) und `ground_truth.json` (korrigierte Referenz, mit
  Provenienz je Sample); analog `benchmark/data/vintage_schellack/`.
- `prepare.py` integriert die neuen Kategorien (keine Degradation — das
  Originalmaterial ist bereits „vintage").
- Der Report zeigt die neuen Kategorien wie jede andere; WER auf
  Walzen-/Schellackqualität wird **erwartungsgemäß deutlich höher** liegen
  als auf Studio-/TTS-Audio — das ist ein ehrliches Robustheits-Maß, kein
  Fehler.

## Abgrenzung / Ehrlichkeit

- **Wachston:** Ground Truth ist eine **eigene, korrigierte Referenz**
  (Vortranskription durch ps-pk-onnx/Whisper, korrigiert durch die
  Projektleitung) — keine unabhängige Studien-Referenz wie bei FQS.
  Die Korrektur ist subjektiv bei schwer verständlichen Passagen; das wird
  im GT-Metadatenfeld `confidence` je Sample vermerkt.
  Rechte: private Sammlung, Audio frei abrufbar; Verwendung als
  Benchmark-Testmaterial ist nach Rücksprache mit dem Betreiber ok,
  eine Weitergabe der Audiodateien außerhalb des Repos ist zu vermeiden
  (Repos bleiben intern/privat).
- **vintage_schellack:** Internet Archive 78rpm-Sammlung, Public Domain —
  Audio-Dateien bleiben lokal (Repos enthalten nur Metadaten/mapping.json,
  wie bei den Walzen).
- Walzen-/Schellackqualität (100 Hz–6 kHz) liegt unterhalb der
  Trainingsverteilung moderner ASR-Modelle; hohe WER sind zu erwarten und
  werden **nicht** weggeglättet (Anti-Gaming-Prinzip des Benchmarks).

## Specs-Delta

`MODIFIED` — `specs/engineering/spec.md`: neue Requirements
