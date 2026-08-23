# Change 022 — ps-auxiliary: Punctuation + Truecasing im Post-Processing-Container

## Problem

Interpunktion und Großschreibung (Truecasing) stecken heute **in den
ASR-Backend-Images**: `crispr-moonshine-de`, `crispr-pk-cpp` und
`crispr-canary` starten den CrispASR-Server mit
`--punc-model fullstop --truecase-model lstm` (Dockerfile-ENV
`CRISPASR_EXTRA_ARGS` bzw. onstart). Drei belegte Nachteile:

1. **Falsche Schicht:** Punc/Truecase ist Post-Processing, nicht ASR.
   Change 020 definiert dafür den `ps-auxiliary`-Container (Diarization +
   Aligner, modell-unabhängig) — genau dort gehört auch die
   Formatierung hin, nicht in jedes `ps-asr-<backend>`-Image.
2. **Startzeit-Verfälschung + Hänger:** Beide GGUFs sind nicht im Image;
   der Server lädt sie bei **jeder frischen Instanz** von HuggingFace.
   Beobachtet 18.08.: Download hing bei 1,3 % über 6 min fest, der
   Server band den Port nicht (Benchmark-Instanz 48057355). Das
   verfälscht Startzeit-Messungen (Netzwerk statt GPU) — ein Confounder
   für Change 021.
3. **Duplikation:** Der Interpunktions-Reranker (`fullstop-punc`,
   XLM-RoBERTa-large) und der Truecaser (`truecaser-de`, lstm) werden
   pro Backend-Image mitgeladen, obwohl sie modell-unabhängig sind.

## Lösung

### Verhaltens-Delta

- **ps-auxiliary-Container wird um den Formatierungs-Dienst erweitert**
  (MODIFIZIERT Change-020-Definition „Supervisor: zwei Prozesse" →
  **drei Prozesse**):
  1. **crispr-diar** — Diarization (CPU-only, empirisch belegt PR #364)
  2. **crispr-align** — Forced Alignment (ggml-hybrid; CPU-vs-GPU-RTF
     offener Messpunkt aus 020 Phase 3)
  3. **punc-dienst (NEU)** — Punctuation + Truecasing: nimmt rohen
     Segment-Text, liefert formatierten Text (Satzzeichen +
     Großschreibung). Endpunkt `POST /v1/text/punctuate`
     `{text, language}` → `{text}`; `/health` je Dienst.
- **Segmentweise Anwendung:** Die Webapp schickt jedes ASR-Segment
  einzeln durch den punc-Dienst — Satzzeichen/Großschreibung ändern die
  Wortreihenfolge nicht, Segment-Grenzen, Wort-Timestamps und
  Sprecher-Zuordnung bleiben gültig.
- **Webapp-Pipeline:** `Upload → ASR (roh) → ps-auxiliary (Diar + Align +
  Punc) → LLM-Template (opt-in, Change 005) → Version/Export`. Das LLM
  arbeitet auf formatiertem Text. Konfiguration über
  `POLYSCHNACK_PS_POST_URL`; solange nicht gesetzt, liefern die
  ASR-Images weiterhin intern punc/truecase (kein Verhaltensbruch).
- **Fehlerverhalten (keine stillen Fehler):** Ist der punc-Dienst nicht
  erreichbar, wird der rohe Text verwendet und am Recording ein
  sichtbares Flag `postprocess_status="punc-fallback"` gesetzt; die
  Transkription selbst bleibt `done`.
- **ASR-Images:** Nach dem ps-auxiliary-Deploy verlieren die Deploy-Images
  `--punc-model`/`--truecase-model` (in den Benchmark-Onstarts von
  Change 021 bereits entfernt — dort misst der Benchmark den rohen
  ASR-Kern).

### Bezug zu anderen Changes

- **Change 020:** Dies ist der Bau-Auftrag für den ps-auxiliary-Container
  (Phase 3-Task „ps-auxiliary-Image") — erweitert um den dritten Dienst.
  Die Diar-CPU-Entscheidung (PR #364) und der Align-CPU-Messpunkt
  bleiben gültig; der punc-Dienst ist CPU-only (kleine Modelle).
- **Change 021:** Benchmark misst rohen ASR-Output (WER via jiwer auf
  normalisiertem Text, punc-unabhängig) — bereits umgesetzt.
- **Change 005:** Bestehende Post-Processing-Capability (LLM-Templates,
  Delivery) bleibt unverändert; ps-auxiliary ist eine zusätzliche Stufe.

## Betroffene Verhaltensbereiche

- **Post-Processing (MODIFIED):** neue Req „Punctuation + Truecasing
  (ps-auxiliary)" — siehe `specs/postprocessing/spec.md`.
- **Transcription (MODIFIED):** Ablauf Req 2 erweitert um die
  ps-auxiliary-Stufe — siehe `specs/transcription/spec.md`.

## Downgrade

- `POLYSCHNACK_PS_POST_URL` entfernen → ASR-interne punc/truecase-Args
  wieder aktiv (Images behalten sie bis zum ps-auxiliary-Deploy);
  ps-auxiliary-Container bleibt für Diar/Align nutzbar.
