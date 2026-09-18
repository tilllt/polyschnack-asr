# Change 201 — Tasks

## 1. Messung (Grundlage)

- [x] `app/ass_export/textfit.py`: Schriftdatei über `fc-match -f %{file}`
      auflösen (`font_name` + Fettschrift), mit Zwischenspeicher
- [x] `text_width(text, font_name, bold, size)` über Pillow (`ImageFont.getlength`)
- [x] Verfügbare Breite aus `play_res_x`, `margin_l`, `margin_r`,
      `outline_width`, `shadow` ableiten
- [x] Fehlende Messmöglichkeit als Fähigkeit melden (`font_available()`), nicht
      verschlucken

## 2. Zeilenbildung nach Breite

- [x] `build_lines(..., fit=True)`: innerhalb der harten Grenzen (Segment-,
      Sprecherwechsel, Satzende) die Wörter so aufteilen, dass die Zeilen
      **möglichst gleich breit** sind
- [x] `words_per_line` bleibt Obergrenze (nie mehr Wörter pro Zeile als eingestellt)
- [x] Groß-/Kleinschreibung geht in die Messung ein
- [x] Ein Wort, das allein breiter als die Zeile ist, bekommt seine eigene Zeile
      (kein Zerhacken von Wörtern)

## 3. Schriftgröße

- [x] Eine Größe je Export: `verfügbare Breite / breiteste Zeile × Referenzgröße`
- [x] Begrenzung auf 0,5×…3× der eingestellten `font_size`
- [x] Warnung `fit_overflow:<n>`, wenn die breiteste Zeile bei der Untergrenze
      nicht passt
- [x] Warnung `fit_unavailable`, wenn nicht gemessen werden kann (dann feste Größe)
- [x] `fit_mode` in `PARAM_SPECS` (`off` | `balanced`, Vorgabe `off`) und in
      `LAYOUT_PARAM_KEYS`, damit der Regler im Dialog erscheint

## 4. Oberfläche

- [x] Beschriftungen `ep_fit_mode`, Werte `ass_pos_off` / `ass_pos_balanced`,
      Warnungen `ass_warn_fit_overflow` / `ass_warn_fit_unavailable` in allen
      drei Sprachen (`pt`, `de`, `en`)

## 5. Container

- [x] `pillow` in `pyproject.toml`, `fonts-liberation` + `fontconfig` im
      Webapp-Image
- [x] Prüfung im Image-Bau: `fc-match` findet Liberation Sans und eine
      Beispielmessung liefert eine Breite > 0 — sonst scheitert der Bau

## 6. Tests

- [x] Einheit: Zeilenbreiten liegen dicht beieinander (ausbalanciert)
- [x] Einheit: keine Zeile über der verfügbaren Breite
- [x] Einheit: `words_per_line` als Obergrenze eingehalten
- [x] Einheit: `off` erzeugt dieselbe ASS wie vorher (feste Größe, feste Wortzahl)
- [x] Einheit: Warnung bei nicht passender Zeile (`fit_overflow`)
- [x] Einheit: ohne Pillow/Schrift bleibt es bei der festen Größe + Warnung
- [ ] Rendertest: Textpixel-Bounding-Box im erzeugten Video füllt die Breite
- [x] Bestehender Test `test_used_params_match_the_rendered_output` muss halten
      (der neue Parameter MUSS die Ausgabe verändern)

## 7. Doku

- [x] `docs/caption-export.md`: Modus beschreiben, Grenzen und Meldungen nennen
- [x] `openspec/changes/201-.../specs/caption-export/spec.md` als Delta

## 8. Ausrollen und abnehmen

- [ ] Deploy, dann echte Aufnahme rendern (Vergleich `off` gegen `balanced`) und
      die Textbreite im Video messen

## Stand 18.09.2026

Umgesetzt und lokal geprüft (noch nicht ausgerollt):

- Kern: `textfit.py` (Messung), `fitwidth.py` (Ausbalancieren + Größe),
  `build_lines(..., measure=, available=)` und `_fit_font_size` im Generator.
- Parameter `fit_mode` (`off` | `balanced`, Vorgabe `off`) in `PARAM_SPECS` und
  `LAYOUT_PARAM_KEYS`; Beschriftungen und Warnungen in allen drei Sprachen.
- Frontend: Warnungen `fit_overflow` / `fit_unavailable` zugeordnet,
  Bundle neu gebaut (`npm test`: 463 grün, Typprüfung sauber).
- Backend: 14 neue Tests + 75 bestehende ASS-Tests grün.
- Image: `fonts-liberation`, `fontconfig`, `pillow`; Prüfung im Bau
  (fc-match + Beispielmessung > 0).

Beim Prüfen gefundene und behobene eigene Fehler (alle durch Tests/Läufe
aufgedeckt, keine stillen):

1. Größe wurde gerundet statt abgerundet → Zeile 1859 px bei 1833 px verfügbar.
2. Zeilenzahl kam aus der Wort-Obergrenze statt aus der Breite → Ausbalancieren
   wirkte nicht (754 gegen 5312 px in einer Aufnahme).
3. Bei mehr berechneten Zeilen als Wörtern entstand eine **leere** Zeile
   (IndexError in `apply_timing`).
4. Der Schwanz konnte über den Rand laufen, weil beim frühen Abbrechen die
   Machbarkeit des Rests nicht geprüft wurde (jetzt mit `_min_lines`-Vorausschau).

Messwerte am Beispiel (1920 px, Ränder 40, Kontur 3, Schatten 1 → 1833 px
verfügbar, gemischte Satzlängen):

| | `off` | `balanced` |
|---|---|---|
| Schriftgröße | 56 px | 108 px |
| Zeilenbreiten | 728…942 px | 1236…1816 px |
