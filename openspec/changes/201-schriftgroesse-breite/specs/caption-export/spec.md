# Caption Export (Change 201 — Ergänzungen)

## ADDED Requirements

### Requirement: Schriftgröße an der Bildschirmbreite ausrichten

- **Parameter:** `fit_mode` (`off` | `balanced`, Vorgabe `off`). Der Regler
  erscheint im Export-Dialog bei allen Presets, weil der Generator ihn
  auswertet (`LAYOUT_PARAM_KEYS`).
- **`off`:** unverändertes Verhalten — feste `font_size`, Umbruch nach
  `words_per_line`.
- **`balanced`:** Die Zeilen werden nach **Breite** ausbalanciert; daraus wird
  **eine** Schriftgröße für den ganzen Export berechnet, die die breiteste
  Zeile ausfüllt. `words_per_line` bleibt als **Obergrenze** für Wörter je
  Zeile erhalten. Harte Grenzen (Sprecherwechsel, Abschnittswechsel, Satzende
  bei `sentence_breaks`) gelten unverändert.
- **Messung:** Die Breite wird mit der Schrift gemessen, die der Renderer
  benutzt (fontconfig-Auflösung wie im Render-Container, Rasterung über
  FreeType). `uppercase`, `bold`, `margin_l`/`margin_r`, `outline_width` und
  `shadow` gehen in die Rechnung ein.
- **Grenzen:** Die berechnete Größe bleibt zwischen 0,5× und 3× der
  eingestellten `font_size`, mindestens 8 px, und wird **abgerundet** (auf-
  gerundet liefe die Zeile über den Rand).
- **Wirksame Größe:** Die Antwort und der ASS-Kopf nennen die tatsächlich
  benutzte Größe — es gibt keine zweite Wahrheit.

#### Scenario: Modus füllt die Breite

- **Akteure:** Besitzer einer Aufnahme mit echten Wortzeiten.
- **Eingaben:** Export mit `fit_mode="balanced"` (Beispiel: `play_res_x=1920`,
  Ränder 40, Kontur 3, Schatten 1 → 1833 px verfügbar).
- **Ergebnis:** Die Schriftgröße ist größer als eingestellt, keine Zeile ist
  breiter als 1833 px, und die breiteste Zeile füllt die Breite weitgehend aus
  (gemessen am Beispiel: 56 px → 108 px, Zeilen 1236–1816 px).
- **Gegenprobe `off`:** Dieselbe Aufnahme bleibt bei der festen Größe und
  derselben ASS-Ausgabe wie vor der Einführung.

#### Scenario: Zeile passt auch mit kleinster Schrift nicht

- **Akteure:** Aufnahme mit einem sehr langen Einzelwort.
- **Ergebnis:** Das Wort steht allein in seiner Zeile (Wörter werden nicht
  zerschnitten), und der Export meldet
  `fit_overflow:<n>` — die Oberfläche zeigt „In n Zeile(n) passt der Text auch
  mit der kleinsten Schrift nicht in die Breite." Es wird **nicht**
  stillschweigend über den Rand geschrieben.

#### Scenario: Messung nicht möglich

- **Akteure:** Betreiber, dessen Image die Schriftmessung nicht kann.
- **Ergebnis:** Der Export bleibt bei der eingestellten `font_size` und meldet
  `fit_unavailable:<grund>`. Der Image-Bau prüft die Fähigkeit (fc-match +
  eine Beispielmessung > 0), damit dieser Fall nicht erst im Betrieb auffällt.
