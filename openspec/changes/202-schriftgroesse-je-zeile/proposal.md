# Change 202 — Schriftgröße je Zeile (Bildschirm füllen, Größe springt)

**Status:** in Arbeit
**Betroffen:** `webapp/app/ass_export/presets.py`,
`webapp/app/ass_export/fitwidth.py`, `webapp/app/ass_export/textfit.py`,
`webapp/app/ass_export/ass_generator.py`,
`webapp/app/ass_export/presets/*.ass.j2`,
`webapp/frontend/src/useLocale.ts`, `docs/caption-export.md`

## Problem

Change 201 hat `fit_mode="balanced"` gebracht: die Zeilen werden nach Breite
ausbalanciert und **eine** Schriftgröße für den ganzen Export füllt die
breiteste Zeile. Damit bleibt eine Wunschvorstellung offen, die 201 bewusst
*ausgeschlossen* hat („Eine Größe je Zeile … war genau nicht gewünscht"):

> Die eingestellte Wortzahl soll **jede** Zeile auf die Bildschirmbreite
> bringen — ein einzelnes Wort also riesig, zehn Wörter kleiner. Die Größe
> springt von Anzeige zu Anzeige. Oben/unten/links/rechts bleibt ein
> Sicherheitsrand („Safe Title") von etwa 5–10 % frei.

Das ist genau das Aussehen, das kurze Social-Media-Untertitel brauchen
(„Full-Screen-Captions"), und es ist mit `balanced` nicht erreichbar: dort
haben alle Zeilen dieselbe Größe, und weil die Größe an der *breitesten* Zeile
hängt, bleibt eine kurze Zeile absichtlich schmal.

## Lösung

Zwei Änderungen, beide additiv (Vorgaben ändern kein bestehendes Preset):

1. **`fit_mode` bekommt einen dritten Wert `per_line`.** Statt einer Größe je
   Export wird die Größe **je Zeile** aus deren eigener Textbreite berechnet und
   als `{\fs…}` an den Zeilen-Anfang geschrieben. Die Zeilenbildung bleibt die
   eingestellte Wortzahl (`words_per_line`); es wird **nicht** nach Breite
   ausbalanciert.
2. **Neuer Parameter `safe_margin_pct`** (Vorgabe 5, 0–20): Sicherheitsrand in
   Prozent **je Seite** — waagerecht als Ränder des ASS-Stils, senkrecht als
   Grenze für die Höhe. `0` stellt den alten, randnahen Stand wieder her.

### Größe je Zeile: Breite **und** Höhe

Die Breite allein genügt nicht: ein einzelnes kurzes Wort („Ich") käme damit auf
eine Schriftgröße von über 1000 px und liefe oben aus dem Bild. Deshalb wird die
Größe nach **zwei** Messungen begrenzt:

* **Breite:** `verfügbare Breite / Zeilenbreite × Referenzgröße` (wie bei 201,
  mit der echten Schrift gemessen).
* **Höhe:** die Tinte der Zeile muss zwischen `margin_v` (unten) und dem oberen
  Sicherheitsrand Platz haben. Die Tintenhöhe wird mit derselben Schrift
  gemessen (`font.getbbox`), nicht als Faktor geraten.

Die kleinere der beiden Größen gewinnt, abgerundet auf ganze Pixel, mit einer
Untergrenze (halbe `font_size`, mindestens 8 px), damit nichts unlesbar wird.
Die Obergrenze 3× aus 201 gilt hier **nicht** — sie würde genau den Sprung
verhindern, der gewünscht ist; die Höhe ist die physikalische Grenze.

### Safe Title

`safe_margin_pct` (0–20, Vorgabe 5) wirkt in **allen** Modi:

* waagerecht: `MarginL`/`MarginR` des ASS-Stils = `max(40 px, pct % von play_res_x)`
* senkrecht: oberer Sicherheitsrand = `pct % von play_res_y`
* in der Breiten-/Höhenrechnung wird derselbe Wert benutzt (eine Wahrheit)

Mit der Vorgabe 5 % wird die Schrift also etwas kleiner als bisher (Ränder
96 px statt 40 px bei 1920 px Breite, verfügbare Breite 1833 → 1721 px). Das ist
gewollt — ein Sicherheitsrand *ist* der Zweck —, wird hier aber ausdrücklich
genannt, weil es auch `balanced` betrifft. `safe_margin_pct=0` stellt das alte
Verhalten (40 px) exakt wieder her.

### Warum der Ränder-Weg und nicht ein zweiter Schalter

`safe_margin_pct` steht in `used_params` und muss laut
`test_used_params_match_the_rendered_output` die Ausgabe in **jeder**
Konfiguration verändern können. Ein Wert, der nur bei aktivem `fit_mode` wirkt,
würde diesen Test zu Recht rot machen (wirkungsloser Regler bei `fit_mode=off`).
Als Stil-Rand wirkt er immer und ist zugleich die ehrlichere Beschreibung:
der Sicherheitsrand ist eine Eigenschaft des Bildes, nicht der Schriftanpassung.

### Benutzerbearbeitbare Vorlagen

Die Größe je Zeile kann nicht im ASS-Stil stehen (der gilt für alle Events),
sondern nur im Event-Text. Damit die Vorlagen (Change 193: auch von Nutzern
geschrieben) das kontrollieren, bekommen **Vorlagen-Variablen** den fertigen Tag:

* `line.fs_tag` — `{\fs108}` oder leer
* `st.fs_tag` — dasselbe je Wort-Schritt (Presets „Aufpoppen" / „Social Media")

Die mitgelieferten Vorlagen setzen ihn an den Anfang des Text-Feldes. Fehlt er
in einer Vorlage, während `per_line` gewählt ist, wird das **gemeldet**
(`fit_tag_missing:<preset>`) und nicht stillschweigend ignoriert: die Ausgabe
wird geprüft, nicht die Konfiguration geglaubt.

## Abnahme

1. Eine Zeile mit einem Wort bekommt eine größere Schrift als eine Zeile mit
   zehn Wörtern; jede Zeile füllt die verfügbare Breite (Toleranz: die
   Vorschubbreite der Messung ist ~11 % breiter als die Tinte — gemessen).
2. Kein Event überschreitet die Höhe (Tinte zwischen unterem Rand und oberem
   Sicherheitsrand) — geprüft am gerenderten Bild, nicht nur in der Rechnung.
3. `safe_margin_pct=0` erzeugt dieselben Ränder wie vor dem Change; `off`
   erzeugt unverändert dieselbe ASS-Datei.
4. Jedes Dialogue-Event trägt genau ein `\fs` (kein Event ohne Größe).
5. `test_used_params_match_the_rendered_output` bleibt grün (beide neuen
   Parameter ändern die Ausgabe in jeder geprüften Konfiguration).
