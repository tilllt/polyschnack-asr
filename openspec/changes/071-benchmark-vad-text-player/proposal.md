# Change 071 — Benchmark-Seite: VAD-Text + aktuelle Methodik + sichtbare Player

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User-Befund (2026-08-21): „Die Texte auf der Benchmark Seite sind
veraltet, es gibt keinen Text für VAD Benchmarks, keine wav Player."

Fakten (Code + Live-API):
1. **Methodik veraltet**: `meta.methodology` kommt aus dem Manifest v2
   (Stand 2026-08-19) und beschreibt NUR den ASR-Benchmark (CommonVoice +
   Piper, 2-Achsen-Matrix). Der VAD-Benchmark (Change 062/064/065: Testset
   V3.1, 235 public Samples, F1/Boundary/FP/RTF) fehlt vollständig.
2. **Kein VAD-Text**: Die VAD-Sektion zeigt nur die (leere) Ergebnistabelle
   + „Noch keine VAD-Ergebnisse…" — keine Erklärung der Metriken, des
   Testsets, der Lizenz-Matrix.
3. **Keine sichtbaren Player**: `openCat` startet `null` → ALLE
   Kategorien zugeklappt → Samples/WAV-Player erst nach manuellem
   Aufklappen sichtbar. Wirkt wie „es gibt keine Player".

## Ziel

1. **Aktuelle Methodik**: Text-Abschnitt erwähnt ASR (WER/CER, 207 Samples,
   v2) UND VAD (Testset V3.1-public, 235 Samples, Metriken F1,
   B-Start/B-Ende, FP-Speech, RTF; held-out geheim).
2. **VAD-Erklärung**: Eigener Text-Block in der VAD-Sektion — was wird
   gemessen, mit welchem Testset (Release v4 + Provenienz-Link), welche
   Modelle produktiv nutzbar sind (Lizenz-Matrix).
3. **Player sofort sichtbar**: Erste Kategorie ist initial geöffnet —
   User sieht Samples + WAV-Player ohne Klick.

## Verhaltens-Delta (IST → SOLL)

- **IST:** Methodik = ASR-only; VAD-Sektion ohne Erklärtext; alle
  Kategorien zugeklappt.
- **SOLL:** Methodik nennt ASR + VAD; VAD-Sektion erklärt Metriken/Testset/
  Lizenzen; erste Kategorie offen (Player sichtbar).

## Umsetzung (Skizze)

1. `BenchmarkPage.tsx`:
   - Methodik-Sektion: zusätzlicher VAD-Absatz (statisch, Frontend —
     Manifest ist Backend-Daten, VAD-Info kommt aus VadResultRow/Release)
   - `VadResultsTable`: Erklär-Block über der Tabelle (Metriken, Testset,
     Lizenz-Hinweis) + Empty-State mit besserem Text
   - `openCat` initial = erste Kategorie-ID (falls Samples existieren)
2. Tests: Kategorie 1 initial offen; VAD-Sektion rendert Erklärtext;
   Empty-State-Text.

## Referenzen

- Change 062 (VAD-Benchmark), 064 (V3.1-Split), 065 (Webapp-Import),
  Manifest v2 (Methodik), Release v4 (vad-benchmark-v3.1-public.zip)
