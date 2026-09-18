# Change 201 — Schriftgröße füllt die Bildschirmbreite

**Status:** in Arbeit
**Betroffen:** `webapp/app/ass_export/presets.py`,
`webapp/app/ass_export/ass_generator.py`, `webapp/app/ass_export/textfit.py` (neu),
`webapp/pyproject.toml`, `webapp/Dockerfile`,
`webapp/frontend/src/useLocale.ts`, `docs/caption-export.md`

## Problem

Die Untertitel haben eine **feste Schriftgröße** (`font_size`, Vorgabe 48) und
brechen nach fester Wortzahl (`words_per_line`, Vorgabe 4). Auf dem Bildschirm
bleibt dadurch regelmäßig viel Breite ungenutzt: eine Zeile mit vier kurzen
Wörtern füllt bei 1920 px vielleicht ein Drittel der Breite, obwohl Platz für
deutlich größere Schrift wäre. Wer größere Untertitel will, muss die
Schriftgröße von Hand hochdrehen — und läuft dann bei der nächsten, längeren
Zeile aus dem Bild.

## Lösung

Ein neuer Parameter **`fit_mode`** (`off` | `balanced`, Vorgabe `off`):

* **`balanced`** — die Zeilen werden nach **Breite** ausbalanciert (Ziel: alle
  Zeilen ungefähr gleich breit, damit eine gemeinsame Schriftgröße sie alle
  ausfüllt), und danach wird **eine** Schriftgröße für den ganzen Export so
  berechnet, dass die breiteste Zeile die verfügbare Breite ausfüllt.
  `words_per_line` bleibt als **Obergrenze** erhalten: es bestimmt, wie viele
  Wörter höchstens in eine Zeile dürfen.
* **`off`** — unverändertes Verhalten (feste Größe, feste Wortzahl), damit
  bestehende Presets und Erwartungen nicht kippen.

### Warum eine gemeinsame Größe und nicht pro Zeile

Eine Größe je Zeile würde bei unterschiedlich langen Wörtern zwischen den
Zeilen springen (mal riesig, mal klein) — das sieht unruhig aus und war genau
nicht gewünscht. Ausbalancierte Zeilen lösen dasselbe Ziel stabil. Zusätzlich
passt es zur Bauweise der Vorlagen: die Schriftgröße steht im ASS-**Stil**,
während der Zeilentext aus **benutzerbearbeitbaren** Vorlagen kommt. Eine
Größe je Zeile müsste als `{\fs…}` in diesen Text hineingeschrieben werden und
würde bei jeder Vorlagenänderung brechen.

### Messung mit der echten Schrift

Die Breite wird nicht geschätzt, sondern mit der Schrift gemessen, die der
Renderer auch benutzt: `fc-match` liefert die Schriftdatei (Arial → Liberation
Sans, wie im Render-Container), gemessen wird mit Pillow (FreeType). Groß- und
Kleinschreibung (`uppercase`) und Fettschrift gehen in die Messung ein, ebenso
die Ränder des Stils (`margin_l` + `margin_r`) und ein Zuschlag für Kontur und
Schatten (`outline_width`, `shadow`), damit die Schrift nicht in den Rand
läuft.

Verfügbare Breite = `play_res_x − margin_l − margin_r − 2 × outline_width − shadow`

### Grenzen und ehrliche Meldung

* Die berechnete Größe wird auf **0,5× bis 3× der eingestellten `font_size`**
  begrenzt — die eingestellte Größe bleibt damit die Richtung, der Modus
  verschiebt sie nur.
* Passt die breiteste Zeile selbst bei der Untergrenze nicht (z. B. ein sehr
  langes Einzelwort), wird **nicht** stillschweigend über den Rand geschrieben:
  der Export meldet die Warnung `fit_overflow:<n>` (n = betroffene Zeilen), die
  die Oberfläche wie die übrigen Warnungen anzeigt.
* Fehlt die Messmöglichkeit (kein Pillow oder keine Schrift auffindbar), wird
  **nicht** auf eine Ersatzgröße ausgewichen: Warnung `fit_unavailable`, und es
  bleibt bei der festen Größe.

## Abnahme

1. Einheitentests: ausbalancierte Zeilen unterscheiden sich in der Breite nur
   wenig; keine Zeile überschreitet die verfügbare Breite; `words_per_line`
   wird als Obergrenze eingehalten; `off` ändert nichts.
2. Rendertest mit echter Ausgabe: Text im erzeugten Video messen (Bounding-Box
   der Textpixel) — die Zeile muss die verfügbare Breite weitgehend ausfüllen
   und innerhalb des Bildes bleiben.
3. Gegenprobe `off`: dieselbe Aufnahme bleibt bei der festen Größe.
