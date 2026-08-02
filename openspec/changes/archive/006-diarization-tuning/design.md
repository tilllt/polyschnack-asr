# Design — Diarization Tuning (006)

## Ziel

Dem User zwei wirkungsvolle Stellschrauben für pyannote geben, ohne das UI
zuzumüllen und ohne das Backend für jeden Pipeline-Parameter zu öffnen.

## Entscheidungen

### 1. UI-übersetzung im Frontend, Backend bekommt fertige pyannote-Werte

- **Entscheidung:** Das Frontend mappt die UI-Stufen auf konkrete Werte
  (`less → 0.4`, `more → 0.05`, `std → undefined`); das Backend akzeptiert
  `diarize_num_speakers` (int) und `diarize_min_duration_off` (float).
- **Warum:** Backend bleibt dumm/typisiert (keine String-Magie wie
  `"less"`), API ist stabil, Sensitivitäts-Stufen können im UI frei
  nachjustiert werden ohne Backend-Deploy. Die Mapping-Funktion
  `diarSensToMinDurationOff()` ist pur und unit-testbar.
- **Alternative verworfen:** „Sensitivität als Enum ans Backend" — würde
  die Werte-Tabelle ins Backend duplizieren und jede Stufenänderung zum
  Backend-Deploy machen.

### 2. `num_speakers` als min=max statt separater min/max-Felder

- **Entscheidung:** Ein Feld „Sprecherzahl" (Auto/1/2/3/4+) → Backend setzt
  `min_speakers = max_speakers = num_speakers`.
- **Warum:** Für den Anwendungsfall („es sind 2") ist die exakte Angabe der
  stärkste Hebel. Min/max-Ranges würden das UI verkomplizieren und verwirren.
- **Alternative verworfen:** Min/Max-Slider — zu technisch, kaum Nutzen
  gegenüber exakter Angabe.

### 3. Werte am Recording speichern

- **Entscheidung:** Beide Werte sind Recording-Spalten (nullable); Transcribe
  UND Re-Transcribe setzen sie; `_recording_to_dict` liefert sie; das UI
  belegt die Menüs beim Öffnen vor.
- **Warum:** Re-Transcribe (die Haupt-Aktion nach dem Anpassen) muss ohne
  erneutes Einstellen dieselben Parameter nutzen. Default `None` = exakt
  bisheriges Verhalten (Pipeline-Default) — kein Breaking Change für
  bestehende Aufnahmen.

### 4. Ausklappbar via `<details>` statt immer sichtbarer Selects

- **Entscheidung:** Ein „Sprecher-Einstellungen"-Summary erscheint nur,
  wenn der 🎙 Speaker-Toggle an ist; Inhalt = zwei Dropdowns.
- **Warum:** Die Transcribe-Zeile ist dicht gepackt; Parameter sind nur
  relevant, wenn Diarization aktiv ist. Weniger kognitive Last.

## Offene Fragen

- Ob `onset`/`offset` (Fein-Tuning) später als dritte Ebene sinnvoll sind —
  bewusst weggelassen (User-Scope „nur 1+2").
- Rückabbildung `min_duration_off → Sensitivitätsstufe` beim Öffnen nutzt
  Schwellen (≥0.3 → less, ≤0.08 → more); exotische Hand-Werte außerhalb
  fallen auf `std` zurück. Für die UI-generierten Werte immer korrekt.
