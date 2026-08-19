# Change 027 — ASR-Backend-Erweiterung: Whisper, WhisperX, Voxtral (Benchmark + PolySchnack-Container)

## Problem

PolySchnack soll je Komponente die **beste verfügbare Alternative** unter
der Haube nutzen — nachgewiesen durch reproduzierbare Benchmarks und
Paper (Change 021, User-Entscheid 2026-08-18). Der aktuelle ASR-Pool
(Parakeet, Canary, Qwen3, ARK, Moonshine) ist NVIDIA-/crispasr-zentriert.
Drei starke Kandidaten fehlen bislang:

1. **Whisper large-v3** (OpenAI, MIT) — bisher nur als Fremdwert aus der
   FQS-Studie referenziert, nicht selbstgemessen; Referenz-Gewinner auf
   schwierigem Audio (FQS 2022, Walzen-Vortranskription).
2. **WhisperX** (m-bain, BSD-2-Clause) — Pipeline: faster-whisper large-v3
   + wav2vec2-Forced-Alignment (Wort-Timestamps) + pyannote-Diarisierung.
   Für PolySchnack interessant wegen **Wort-genauer Timestamps**
   (Aligner-Rolle), nicht als besseres Transkriptionsmodell.
3. **Voxtral-Mini-4B-Realtime-2602** (Mistral, Apache-2.0, Feb 2026) —
   aktuellstes Voxtral, 13 Sprachen inkl. Deutsch, „kompetitiv zu
   führenden Offline-Modellen" (Modellkarte, Fleurs DE 6,19 % @480 ms).

Die Benchmark-Erweiterung wurde bislang als **Ad-hoc-Skript-Patch**
vorangetrieben (Suite-Backends `whisper-large-v3`, `voxtral-mini-realtime`).
Es fehlt ein geplanter, dokumentierter Weg — inklusive der **Einbindung
als PolySchnack-Backend-Container** (Docker-Image, Compose-Service,
GUI-Auswahl) und des **kommerziellen Lizenz-Checks** (Change-021-Methode).

## Ziel

1. **Selbstgemessene Benchmark-Werte** für Whisper large-v3, WhisperX und
   Voxtral auf identischem Audio (alle Manifest-Kategorien de/en):
   WER, RTF, Kosten, VRAM — reproduzierbar über die Suite.
2. **Container-Einbindung** in den PolySchnack-Stack als wählbare
   Backends (`polyschnack-asr-{whisper,whisperx,voxtral}`): OpenAI-
   kompatible API, Health-Endpoint, Compose-Service, GUI-Backend-Liste,
   GPU-Ressourcenlimits.
3. **Kommerzieller Lizenz-Check** je Modell/Komponente (inkl. der
   wav2vec2-Alignment-Modelle — viele deutsche xlsr-Checkpoints sind
   CC-BY-NC und damit für das kommerzielle Produkt unbrauchbar).
4. Entscheidungen mit Quellen in `docs/component-decisions.md`
   (Re-Evaluation bei Releases, Change-021-Methode).

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- PolySchnack-GUI: neue Backend-Optionen (Whisper large-v3, WhisperX,
  Voxtral) im Transkriptions-Dialog, sofern Benchmark + Lizenz das
  rechtfertigen (Entscheidung in component-decisions.md).
- WhisperX bringt optional Wort-Zeitstempel in die Segment-Ausgabe
  (Aligner-Qualität); Diarisierung bleibt beim bestehenden
  Diar-Backend (keine Duplikation).
- Benchmark-Report enthält die neuen Backends mit selbstgemessenen
  Werten (keine reinen Fremdwerte mehr).
- Suite unterstützt `--instance`-Reuse (bereits implementiert) und die
  neuen Backend-Definitionen (bereits registriert); formalisiert.

## Abgrenzung / Ehrlichkeit

- **WhisperX ändert den Transkriptionstext nicht** (gleiche Whisper-
  Modelle) — als ASR-Backend gemessen liefert es large-v3-Qualität;
  der Mehrwert (Alignment/Diar) wird getrennt bewertet.
- **Voxtral-Mini-4B-Realtime** ist ein Realtime-Modell (streaming,
  WebSocket empfohlen); der Suite-Einsatz über die REST-Transcriptions-
  API ist zu verifizieren (vLLM `SupportsTranscription`).
- **Lizenz-Hürden:** Deutsche wav2vec2-Alignment-Modelle (z. B.
  `jonatasgrosman/wav2vec2-large-xlsr-53-german`) sind häufig
  CC-BY-NC-4.0 → für kommerzielle Nutzung nicht zulässig. Geeignetes
  deutschsprachiges Alignment-Modell mit kommerziell-tauglicher Lizenz
  ist Voraussetzung für die WhisperX-Einbindung (sonst nur interne
  Messung, wie beim Zwirner-Korpus-Handling).
- Benchmark-Werte der Suite sind **eigene Messungen** (identisches
  Audio, gleiche Normalisierung wie die übrigen Backends) — direkt
  vergleichbar mit den Kommerzwerten aus Change 024.

## Specs-Delta

`ADDED` — REQ-BENCH-032/033/034/035 (Suite-Backends, Container-Einbindung,
Lizenz-Check, Entscheidungs-Doku)
