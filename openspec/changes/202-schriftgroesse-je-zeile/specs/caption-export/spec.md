# Caption Export (Change 202 — Ergänzungen)

## ADDED Requirements

### Requirement: Schriftgröße je Zeile (Bildschirm füllen)

- **Parameter:** `fit_mode` erhält den dritten Wert `per_line`
  (`off` | `balanced` | `per_line`, Vorgabe weiterhin `off`).
- **Wirkung:** Die Zeilenbildung bleibt bei der eingestellten Wortzahl
  (`words_per_line`) und den harten Grenzen (Segment-, Sprecherwechsel,
  Satzende). Für **jede Zeile** wird die Schriftgröße aus ihrer eigenen
  Textbreite berechnet, so dass sie die verfügbare Breite ausfüllt; ein Wort in
  der Zeile ist damit riesig, zehn Wörter sind kleiner. Die Größe steht als
  `{\fs…}` am Anfang des Event-Textes (nicht im Stil, der für alle Events gilt).
- **Höhengrenze:** Die Größe wird zusätzlich so begrenzt, dass die **gemessene**
  Tintenhöhe der Zeile zwischen `margin_v` (unten) und dem oberen
  Sicherheitsrand Platz hat. Die kleinere der beiden Größen gewinnt.
- **Rundung und Grenzen:** abgerundet auf ganze Pixel; Untergrenze
  `max(8, 0.5 × font_size)`; **kein** 3×-Deckel (der würde den gewünschten
  Sprung verhindern). Passt eine Zeile auch bei der Untergrenze nicht, meldet
  der Export `fit_overflow:<n>`.
- **Ohne Messmöglichkeit:** wie bei `balanced` — `fit_unavailable`, feste
  Größe, und `fit_mode` erscheint nicht im Dialog.

#### Scenario: Ein Wort gegen zehn Wörter

- **Akteure:** Besitzer einer Aufnahme mit echten Wortzeiten.
- **Eingaben:** Export mit `per_line`, `words_per_line=1` bzw. `10`,
  `play_res_x=1920`, `safe_margin_pct=5`.
- **Ergebnis:** Die Ein-Wort-Zeile bekommt eine deutlich größere Schrift als
  die Zehn-Wort-Zeile; beide füllen die verfügbare Breite (Toleranz: die
  gemessene Tinte erreicht mindestens ~85 % der Vorschubbreite, der Rest ist
  Seitenrand der Glyphen und Abrundung). Keine Zeile läuft über den Rand, keine
  über die Höhengrenze hinaus.
- **Gegenprobe `off`:** unveränderte ASS-Datei (feste Größe, kein `\fs`-Tag).

### Requirement: Sicherheitsrand (Safe Title) in Prozent

- **Parameter:** `safe_margin_pct` (int, Vorgabe **5**, Bereich 0–20),
  Sicherheitsrand in Prozent **je Seite**.
- **Waagerecht:** `MarginL`/`MarginR` des ASS-Stils =
  `max(40 px, pct % von play_res_x)`; dieselbe Breite geht in die
  Schriftberechnung ein (eine Wahrheit, nicht zwei).
- **Senkrecht:** oberer Sicherheitsrand = `pct % von play_res_y` — er begrenzt
  die Tintenhöhe (siehe oben).
- **Geltung:** in **allen** Modi. `0` stellt den vorherigen Stand
  (40 px Ränder) exakt wieder her; die Vorgabe 5 verkleinert auch `balanced`
  leicht (verfügbare Breite 1833 → 1721 px bei 1920 px), weil die Ränder
  wirken.

#### Scenario: Sicherheitsrand wirkt auch ohne Schriftanpassung

- **Akteure:** Nutzer, der `fit_mode=off` fährt und nur den Rand setzen will.
- **Eingaben:** `safe_margin_pct=10` bei `play_res_x=1920`.
- **Ergebnis:** Der ASS-Kopf nennt `MarginL=192,MarginR=192`; die Untertitel
  sind im gerenderten Video um 10 % der Breite eingerückt.
- **Gegenprobe:** `safe_margin_pct=0` → `MarginL=40,MarginR=40` wie vor dem
  Change.

### Requirement: Vorlagen geben die Größe je Zeile weiter

- **Variablen:** Jede Zeile bietet `line.fs_tag`, jeder Wort-Schritt
  `st.fs_tag` — `{\fs108}` bzw. leer (bei `off`/`balanced`).
- **Mitgelieferte Vorlagen** (`classic`, `karaoke`, `highlight`, `kinetic`,
  `modern`) setzen den Tag am Anfang des Text-Feldes.
- **Fremde Vorlage ohne Platzhalter:** Der Export meldet
  `fit_tag_missing:<preset>` — es wird nicht stillschweigend ohne Wirkung
  exportiert.
- **Absicherung:** Ein Test prüft an der erzeugten Datei, dass bei `per_line`
  **jedes** Dialogue-Event genau ein `\fs` trägt.

#### Scenario: Vorlage ohne Platzhalter

- **Akteure:** Nutzer mit eigener Vorlage aus Change 193.
- **Eingaben:** `fit_mode=per_line` mit einer Vorlage ohne `{{ line.fs_tag }}`.
- **Ergebnis:** Die Datei wird erzeugt (kein Absturz), der Dialog zeigt den
  Hinweis, dass die Vorlage die berechnete Größe nicht übernimmt.
