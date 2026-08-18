# Engineering

## ADDED Requirements

### Requirement: Komponenten-Auswahl nach Evidenz

- **Geltungsbereich:** Alle ML- und Infrastruktur-Komponenten von
  PolySchnack (ASR-Modelle, Diarization, Forced Alignment, TTS,
  GPU-/Inference-Backends, Post-Processing).
- **Ablauf:** Vor dem Einsatz oder Wechsel einer Komponente wird eine
  Kandidaten-Evidenz erstellt: (1) Recherche aus Papern, veröffentlichten
  Benchmarks und offizieller Modell-Dokumentation, (2) reproduzierbarer
  Benchmark auf eigener Testaufnahme (Qualität + RTF, getrennt nach
  CPU/GPU und Quantisierung), (3) Lizenz-Check mit Fokus auf
  kommerzielle Nutzung.
- **Pflicht-Dokumentation:** Jede Entscheidung wird mit Ergebnis und
  Quellen in den Decision-Log eingetragen (Datei im Repo); eine
  Entscheidung ohne Quellenbeleg ist nicht zulässig.
- **Re-Evaluation:** Bei neuen relevanten Releases oder Kandidaten wird
  die Entscheidung mit demselben Benchmark überprüft und der Log
  aktualisiert.

#### Scenario: Neue Aligner-Kandidaten

- **Akteure:** Entwickler, Decision-Log.
- **Eingaben:** Kandidaten (z. B. MFA, WhisperX, Seamless), eigene
  deutsche Testaufnahme mit manuell geprüften Wortgrenzen.
- **Ergebnis:** WBE/UBE + RTF je Kandidat (CPU/GPU × Quantisierung);
  Entscheidung („Qwen3 bleibt" oder Wechsel) mit Quellen im Log;
  Seamless scheidet bereits im Lizenz-Check aus (CC-BY-NC).

#### Scenario: Wechsel einer Komponente

- **Akteure:** Entwickler, Reviewer.
- **Eingaben:** Vorschlag „Komponente X durch Y ersetzen".
- **Ergebnis:** Ohne Benchmark/Paper-Evidenz, die Y besser belegt, wird
  der Wechsel abgelehnt; mit Evidenz wird er umgesetzt und im Log
  dokumentiert.

#### Scenario: Neues Release einer genutzten Komponente

- **Akteure:** Entwickler.
- **Eingaben:** Release-Hinweis (z. B. neues ASR-Modell, neuer
  Backend-Anbieter-Preis).
- **Ergebnis:** Gleiche Testaufnahme wird erneut gemessen; nur bei
  messbarem Vorteil wird gewechselt, sonst bleibt der Stand und der Log
  wird mit „erneut geprüft, kein Wechsel" aktualisiert.
