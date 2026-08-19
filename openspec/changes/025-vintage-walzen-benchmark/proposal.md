# Change 025 — Benchmark-Erweiterung: historische deutsche Aufnahmen (vintage_walzen + Zwirner-Korpus)

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
   (Whisper-Vortranskription + manuelle Korrektur durch Projektleitung,
   bereits zugesagt).
2. **Zwirner-Korpus „Deutsche Mundarten"** (DGD, IDS Mannheim): Tonband-
   aufnahmen deutscher Dialekte, aufgenommen 1955–1970 in BRD und DDR
   (~570 Aufnahmen à ~20 min, Erhebung durch das Deutsche Spracharchiv
   unter Eberhard Zwirner), **mit orthographischen/phonetischen
   Transkriptionen** in der DGD. Zugang über kostenlose Registrierung
   (Forschung und Lehre).

## Ziel

1. Echte historische deutsche Aufnahmen als Benchmark-Kategorien
   (`vintage_walzen` und — nach Lizenzklärung — `zwirner_dialekt`)
   in den PolySchnack-Benchmark aufnehmen.
2. Ground-Truth-Workflow für Quellen ohne Transkript etablieren:
   Whisper-Vortranskription → Korrektur durch die Projektleitung →
   Review → `ground_truth.json` (dokumentiert, nachvollziehbar).
3. Alle eigenen Backends auf den neuen Kategorien messen (WER/RTF) und
   die Ergebnisse in Report, Decision-Log und Businessplan aufnehmen
   (Robustheit auf historischem Material).

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Der Benchmark enthält neue Subsets `vintage_walzen` (33 Samples,
  gesprochene Walzen 1898–1914) und ggf. `zwirner_dialekt` (Auswahl aus
  dem Zwirner-Korpus, sobald Zugang/Lizenz geklärt).
- `benchmark/data/vintage_walzen/` mit `audio/`, `hypotheses_whisper.json`
  (Vortranskription) und `ground_truth.json` (korrigierte Referenz, mit
  Provenienz je Sample).
- `prepare.py` integriert die neuen Kategorien (keine Degradation — das
  Originalmaterial ist bereits „vintage").
- Der Report zeigt die neuen Kategorien wie jede andere; WER auf
  Walzenqualität wird **erwartungsgemäß deutlich höher** liegen als auf
  Studio-/TTS-Audio — das ist ein ehrliches Robustheits-Maß, kein Fehler.

## Abgrenzung / Ehrlichkeit

- **Wachston:** Ground Truth ist eine **eigene, korrigierte Referenz**
  (Vortranskription durch faster-whisper large-v3, korrigiert durch die
  Projektleitung) — keine unabhängige Studien-Referenz wie bei FQS.
  Die Korrektur ist subjektiv bei schwer verständlichen Passagen; das wird
  im GT-Metadatenfeld `confidence` je Sample vermerkt.
  Rechte: private Sammlung, Audio frei abrufbar; Verwendung als
  Benchmark-Testmaterial ist nach Rücksprache mit dem Betreiber ok,
  eine Weitergabe der Audiodateien außerhalb des Repos ist zu vermeiden
  (Repos bleiben intern/privat).
- **Zwirner-Korpus:** DGD-Nutzungsbedingungen sind auf **wissenschaftliche
  Zwecke** ausgerichtet. Kommerzielle Nutzung/Veröffentlichung von
  Audio-/Transkript-Ausschnitten im öffentlichen Repo ist **vorab zu
  klären** (DGD-Support). Bis zur Klärung: nur interne Messung, keine
  Audio-/Transkript-Dateien im Repo, Ergebnisse im Report als
  „nicht veröffentlicht, Lizenzprüfung offen" markiert.
- Walzenqualität (100 Hz–5 kHz) liegt unterhalb der Trainingsverteilung
  moderner ASR-Modelle; hohe WER sind zu erwarten und werden **nicht**
  weggeglättet (Anti-Gaming-Prinzip des Benchmarks).

## Specs-Delta

`MODIFIED` — `specs/engineering/spec.md`: neue Requirements
