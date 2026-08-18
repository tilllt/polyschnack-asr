# Change 021 — Evidenzbasierte Komponentenwahl („Best available under the hood")

## Problem

Komponenten des PolySchnack-Stacks sind teils nach Historie oder
Verfügbarkeit gewählt worden, nicht nach belegter Eignung — und Wechsel
passierten ohne Vergleichs-Benchmarks. Beispiele aus 2026-08:

- **Diarization:** Erst der GPU-Versuch (CrispStrobe/CrispASR#364) hat
  durch Messung belegt, dass CPU schneller ist als GPU — die Annahme
  „GPU ist automatisch besser" hielt der Messung nicht stand.
- **Aligner:** Qwen3-ForcedAligner ist im Einsatz, aber es gab keinen
  belastbaren deutschen Benchmark gegen Alternativen (MFA, WhisperX,
  Seamless); Seamless scheidet wegen CC-BY-NC aus — erst die Recherche
  hat das sichtbar gemacht.
- **ASR-Backends:** polyschnack-benchmark misst WER, aber eine
  systematische Kandidaten-Evidenz inkl. Lizenz-Check fehlt.

Ohne Evidenzpflicht wiederholen sich Bauchgefühl-Entscheidungen und
verpasste bessere Optionen.

## Ziel (User-Entscheid 2026-08-18)

**Jedes Teil des PolySchnack-Projektes nutzt die jeweils beste verfügbare
Komponente unter der Haube — nachgewiesen durch Benchmarks und Paper.**

Das gilt für alle ML-/Infrastruktur-Komponenten: ASR-Modelle,
Diarization, Forced Alignment, TTS, GPU-/Inference-Backends,
Post-Processing.

## Methode (verbindlich für jede Komponenten-Entscheidung)

1. **Recherche:** Paper, veröffentlichte Benchmarks und offizielle
   Modell-Dokumentation sammeln; Lizenzen prüfen (kommerzielle Nutzung
   muss erlaubt sein — z. B. Seamless CC-BY-NC = Ausschluss).
2. **Reproduzierbarer Benchmark:** Kandidaten auf derselben eigenen
   Testaufnahme messen — Qualität (WBE/UBE, WER, …) UND Geschwindigkeit
   (RTF), getrennt nach CPU/GPU und Quantisierung. Keine fremden
   Leaderboards allein als Entscheidungsbasis.
3. **Entscheidung dokumentieren:** Ergebnis + Quellen in den
   Decision-Log (siehe tasks.md); Entscheidung bleibt nachvollziehbar.
4. **Re-Evaluation:** Bei relevanten neuen Releases oder neuen Kandidaten
   wird die Entscheidung überprüft (Leichtgewicht: gleicher Benchmark,
   gleiche Metrik).

## Verhältnis zu anderen Changes

- Change 020 (Remote-Inference-Worker): dessen Backend- und
  GPU-Klassen-Entscheidungen (Diar CPU-only, Aligner-Messpunkt,
  vast/theta-Evidenz) sind erste Anwendungen dieses Prinzips.
- polyschnack-benchmark (separates Repo): bestehende ASR-WER-Messung
  wird um die hier definierten Messpunkte ergänzt.
