## ADDED Requirements

### Requirement: Punctuation + Truecasing (ps-auxiliary, punc-dienst)

- **Ablauf:** Nach der ASR-Stufe formatiert der punc-dienst im
  `ps-auxiliary`-Container den rohen Transkriptionstext (Satzzeichen +
  Großschreibung), **segmentweise** (je Segment ein Request), damit
  Segment-Grenzen, Wort-Timestamps und Sprecher-Zuordnung erhalten
  bleiben. Endpunkt: `POST /v1/text/punctuate` `{text, language}` →
  `{text}`; Readiness `GET /health`. Konfiguration über
  `POLYSCHNACK_PS_POST_URL` (leer = Stufe inaktiv, ASR-Image liefert
  intern punc/truecase).
- **Reihenfolge:** ASR (roh) → ps-auxiliary (Diar/Align + Punc) →
  LLM-Template → Version/Export. Das LLM arbeitet auf formatiertem Text.
- **Status:** `postprocess_status ∈ none|punc-done|punc-fallback` am
  Recording; `punc-fallback` = punc-dienst nicht erreichbar → roher
  Text, Transkription bleibt `done` (sichtbar, kein stiller Fehler).
- **Architektur:** `ps-auxiliary/` (Supervisor: crispr-diar :5098,
  crispr-align :5099, punc-dienst :5100 — FastAPI + CrispASR-Python-
  Binding `PuncModel`, CPU-only, GGUFs im Image); Webapp:
  `service.py::process_recording`, punc-Client in `webapp/app/`.

#### Scenario: Formatierte Transkription

- **Akteure:** User transkribiert mit konfiguriertem ps-auxiliary.
- **Eingaben:** `POST /api/recordings/{id}/transcribe` (beliebiges Backend).
- **Ergebnis:** Segmente enthalten Satzzeichen + Großschreibung;
  `postprocess_status="punc-done"`; Timestamps/Sprecher unverändert.

#### Scenario: punc-dienst nicht erreichbar

- **Akteure:** User transkribiert, punc-dienst ist gestoppt.
- **Eingaben:** Transcribe mit `POLYSCHNACK_PS_POST_URL` gesetzt.
- **Ergebnis:** Transkription in rohem Text (ohne Satzzeichen),
  `postprocess_status="punc-fallback"` sichtbar; Status `done`, kein
  Job-Fehler.
