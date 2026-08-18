## MODIFIED Requirements

### Requirement: Transkribieren & Retranskribieren

- **Stufen-Ablauf (Change 022):** ASR liefert rohen Text (ohne
  Satzzeichen/Großschreibung); danach formatiert die ps-post-Stufe
  (punc-dienst, siehe postprocessing „Punctuation + Truecasing") die
  Segmente — segmentweise, sofern `POLYSCHNACK_PS_POST_URL` gesetzt.
  Diarization/Alignment laufen wie gehabt (crispr-diar/crispr-align).
  LLM-Template (opt-in) folgt auf formatiertem Text.
  `postprocess_status ∈ none|punc-done|punc-fallback` am Recording
  (punc-fallback = ps-post nicht erreichbar, roher Text, Status bleibt
  `done`).
- **Ergebnis (unverändert):** `status` durchläuft
  `queued → processing → done|failed`; Fortschritt via
  WebSocket/`progress_pct`; Ergebnis (text, segments, language,
  duration) in der DB.

#### Scenario: Formatierte Segmente nach ASR

- **Akteure:** Besitzer; `POLYSCHNACK_PS_POST_URL` konfiguriert.
- **Eingaben:** Transcribe (Backend ohne native Interpunktion).
- **Ergebnis:** Segmente mit Satzzeichen + Großschreibung;
  `postprocess_status="punc-done"`; Wort-Timestamps und
  Sprecher-Zuordnung unverändert.
