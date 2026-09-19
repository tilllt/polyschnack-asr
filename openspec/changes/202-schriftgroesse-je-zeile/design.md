# Change 202 — Design

## Entscheidungen und ihre Begründung

### D1 — Neuer Wert statt neuer Parameter

`fit_mode` beschreibt bereits „wie wird die Schrift an das Bild angepasst".
Ein zweiter Parameter (`fit_per_line: bool`) hätte eine unmögliche Kombination
erlaubt (`balanced` **und** `per_line` gleichzeitig). Die Auswahlwerte sind damit
`off` | `balanced` | `per_line`.

### D2 — Kein Ausbalancieren im Modus `per_line`

`per_line` füllt **die Zeile**, die die eingestellte Wortzahl ergibt. Würde
zusätzlich nach Breite ausbalanciert, änderte sich die Zahl der Wörter je Zeile
und damit das Aussehen — genau das will der Modus nicht. Zeilenbildung bleibt
also bei `words_per_line` plus den harten Grenzen (Segment-, Sprecherwechsel,
Satzende), Ausbalancieren nur bei `balanced`.

### D3 — Höhe wird gemessen, nicht geschätzt

Sonde (`probe_lineheight2.py`, libass über ffmpeg, 1920×1080, Bold, Kontur 3,
Schatten 1, MarginV 60) — Tinte je `font_size`:

| Text | Höhe bei 200 px | in em |
|---|---|---|
| „Ich" | 132 px | 0,660 |
| „WEG" | 127 px | 0,635 |
| „Hallo Welt" | 132 px | 0,660 |
| „Häggy Wüst" | 163 px | 0,815 |
| „ÄÖÜgjpqy" | 192 px | 0,960 |

Die Tintenhöhe hängt also stark vom Text ab (0,64–0,96 em) — ein fester Faktor
(„1,2 em") wäre bei „ÄÖÜgjpqy" zu knapp und bei „Ich" zu streng. Deshalb wird
die Tintenhöhe mit derselben Schrift gemessen wie die Breite
(`PIL.ImageFont.getbbox`), je Zeile.

Die Messung der **Breite** ist eine Vorschubbreite (advance width): bei
„Hallo Welt" 963 px gegen 852 px Tinte (Verhältnis 0,885, gemessen). Die Zeile
füllt die Breite damit zu ~88–95 %; die letzten Prozentpunkte bleiben aus
demselben Grund frei wie bei 201 (Abrundung, Seitenränder der Glyphen) und sind
in den Tests als Toleranz hinterlegt statt schöngerechnet.

### D4 — Rundung und Grenzen

* **Abrunden** (wie 201): aufgerundet läuft die Zeile über den Rand.
* Untergrenze: `max(8, floor(0.5 × font_size))`. Passt selbst das nicht, wird
  die Zeile gemeldet (`fit_overflow:<n>`) — nicht still über den Rand
  geschrieben.
* Obergrenze: die Höhe (D3). Kein 3×-Deckel wie bei `balanced`.
* Die eingestellte `font_size` bleibt im ASS-Stil stehen und ist damit die
  Untergrenze/Richtung; jedes Event trägt zusätzlich sein eigenes `\fs`.

### D5 — Safe Title über die Stil-Ränder

`safe_margin_pct` (Vorgabe 5, 0–20) → `MarginL = MarginR = max(40, round(play_res_x × pct / 100))`,
oberer Sicherheitsrand `round(play_res_y × pct / 100)`.
Vorteile: wirkt in allen Modi (Test `used_params_match_the_rendered_output`
bleibt ehrlich), ist im ASS-Kopf sichtbar, und `0` reproduziert exakt den
Vorher-Stand (40 px).

### D6 — Tag statt Stil

Die Größe je Zeile steht als `{\fs…}` im Event-Text. Die Vorlagen erhalten dafür
`line.fs_tag` / `st.fs_tag` (leer außer bei `per_line`). Damit bleibt die
Eigenschaft „Vorlagen sind Nutzerdaten" gewahrt: wer eine eigene Vorlage
schreibt, entscheidet mit dem Platzhalter, ob die Größe je Zeile sichtbar wird.
Fehlt der Tag bei gewähltem `per_line`, meldet der Export `fit_tag_missing` —
die Datei wird geprüft, nicht die Absicht.

### D7 — Was nicht geändert wird

* `off` erzeugt weiterhin dieselbe ASS-Datei (der Tag ist leer).
* `balanced` rechnet unverändert, abgesehen vom Sicherheitsrand.
* Kein neues Paket, keine neue Abhängigkeit (Pillow ist seit 201 da).
