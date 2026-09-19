# Change 202 — Tasks

## 1. Parameter

- [ ] `fit_mode` um `per_line` erweitern (`PARAM_SPECS`)
- [ ] `safe_margin_pct` in `PARAM_SPECS` (int, Vorgabe 5, 0–20)
- [ ] `LAYOUT_PARAM_KEYS` und `STYLE_PARAM_KEYS` ergänzen (Regler im Dialog,
      Stil-Ränder)
- [ ] `fit_mode` weiterhin nur listen, wenn Textmessung möglich ist

## 2. Messung

- [ ] `textfit.text_height()` (Tintenhöhe über `getbbox`, gleiche Schrift,
      gleicher Zwischenspeicher wie `text_width`)
- [ ] Verfügbare Höhe: `play_res_y − margin_v − oberer Sicherheitsrand`

## 3. Rechnung

- [ ] `fitwidth.per_line_sizes(available_w, available_h, widths, heights, base)`
      — reine Rechnung, je Zeile `(größe, überlauf)`
- [ ] Abrunden, Untergrenze `max(8, 0.5 × base)`, Obergrenze aus der Höhe
- [ ] Tests der reinen Rechnung ohne Schrift

## 4. Generator

- [ ] Stil-Ränder aus `safe_margin_pct` (waagerecht), oberer Rand (senkrecht)
- [ ] Zeilenbildung: `measure` nur bei `balanced` (kein Ausbalancieren bei `per_line`)
- [ ] `fs_tag` je Zeile/Schritt in den Vorlagen-Kontext
- [ ] Warnung `fit_overflow:<n>` wie bisher, neu `fit_tag_missing:<preset>`
- [ ] Prüfung der AUSGABE: jedes Event genau ein `\fs`, wenn `per_line` aktiv

## 5. Vorlagen

- [ ] `classic`, `karaoke`, `highlight`, `kinetic`, `modern`: `{{ line.fs_tag }}`
      bzw. `{{ st.fs_tag }}` am Anfang des Text-Feldes
- [ ] `off`/`balanced` unverändert (Tag ist leer)

## 6. Oberfläche

- [ ] `ep_safe_margin_pct`, Wert `ass_pos_per_line`, Warnung
      `ass_warn_fit_tag_missing` in **allen drei** Sprachen (pt, de, en)
- [ ] Warnungstext in `warningText()` (sonst Rohtext im Dialog)
- [ ] `npm run build`, `frontend/dist` mitcommitten

## 7. Tests

- [ ] Einheit: ein Wort → größer als zehn Wörter (echte Schrift)
- [ ] Einheit: jede Zeile füllt die Breite (Toleranz ~0,85 der Vorschubbreite)
- [ ] Einheit: Höhengrenze greift (kurzes Wort wird nicht höher als erlaubt)
- [ ] Einheit: `safe_margin_pct=0` → Ränder 40 px (Vorher-Stand)
- [ ] Einheit: `per_line` schreibt in **jedes** Event ein `\fs`
- [ ] Einheit: `off` erzeugt unverändert dieselbe ASS wie vorher
- [ ] Rendertest (libass): Tinte bleibt innerhalb des Sicherheitsrands
- [ ] `test_used_params_match_the_rendered_output` grün
- [ ] Bestehende 201-Tests grün (gegenprobe `balanced`)

## 8. Doku

- [ ] `docs/caption-export.md`: dritter Wert, Safe Title, Höhengrenze,
      Vorlagen-Platzhalter, Messwerte

## 9. Ausrollen

- [ ] Commit + Push (vorher `ci_cancel_running.sh`)
- [ ] CI-Jobs beobachten (`scripts/ci_watch_job.py`)
- [ ] Webapp auf der KI-Box ausrollen, Fähigkeit + Regler live prüfen
- [ ] Status mit Live-Werten nachtragen
