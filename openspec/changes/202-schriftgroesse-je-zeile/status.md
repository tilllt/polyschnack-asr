# Change 202 — Status

**Stand:** implementiert, Tests grün, CI und Ausrollen laufen (siehe unten).

## Was gebaut ist

| Teil | Ort |
|---|---|
| `fit_mode="per_line"`, `safe_margin_pct` | `app/ass_export/presets.py` |
| Rechnung je Zeile (Breite + Zeilenbox) | `app/ass_export/fitwidth.py:per_line_sizes` |
| Höhen-/Boxmessung | `app/ass_export/textfit.py` (`text_height`, `line_box_height`) |
| Verdrahtung, Rand, `fs_tag`, Meldungen | `app/ass_export/ass_generator.py` |
| Platzhalter in den Vorlagen | `app/ass_export/presets/*.ass.j2` |
| Beschriftungen (pt/de/en), Warnung | `frontend/src/useLocale.ts`, `ExportDialog.tsx` |
| Doku | `docs/caption-export.md` |

## Messwerte (lokal, 1920 × 1080, Ränder 96 px → 1721 px verfügbar)

Beispielaufnahme: „Ich", kurze Wörter und ein Wortungeheuer.

* `per_line`, ein Wort je Zeile: 830 / 830 / 830 / 814 / 543 / 761 / 830 / 720 /
  673 / 78 px — der Sprung ist deutlich (Faktor ~11 zwischen kurz und lang).
* `per_line`, vier Wörter je Zeile: 234 / 164 / 69 px.
* `off`, `safe_margin_pct=0`: keine `\fs`-Tags, Ränder 40/40 px wie vor 202.
* Gerendert (libass, 640 × 360): Tinte bleibt im Sicherheitsrand, eine Zeile,
  kein Umbruch — geprüft in `tests/test_ass_export_fit_perline.py`.

### Der Fehler, der beim Messen auffiel

Erster Anlauf begrenzte die Höhe über die **Tinte** (Pillow-`getbbox`). Gerendert
wurde sichtbar: „ist" bei `font_size=1212` (PlayRes 1080) ragte bis Zeile 0 des
Bildes und wurde oben abgeschnitten, weil libass die ganze **Zeilenbox**
(Auf- + Abstieg ≈ 1,14 em) reserviert — bei „ist" sind das 1,14 em, obwohl die
Tinte nur 0,78 em hoch ist. Danach: Grenze = `max(Tinte, Zeilenbox)`. Ohne die
Renderprüfung wäre das durchgegangen (die Rechnung sah in sich stimmig aus).

## Tests

* Neu `tests/test_ass_export_fit_perline.py`: 24 Tests (reine Rechnung,
  Grenzfälle, Sicherheitsrand, Event-Invarianten, Vorlage ohne Platzhalter,
  libass-Rendertest).
* Bestand: `tests/test_ass_export.py` (inkl.
  `test_used_params_match_the_rendered_output`), `test_ass_export_fitwidth.py`,
  `test_ass_export_render.py` — 90 Tests grün.
* Frontend: `ExportDialog.test.tsx` 14 Tests grün, `npm run build` ohne
  Typfehler; alle drei Sprachen haben 464 Schlüssel (neue in allen dreien).

## CI und Ausrollen — erledigt

* Commit `a87f56d` (Pipeline `5382`, rot: s. o.) → Korrektur `af8399a`
  (Pipeline `5383`): `test-webapp` **success** (857 s), `build-webapp`
  **success** (161 s, Image in Harbor), `mirror-github` success,
  `grep-gate` success; `test-frontend` existiert in dieser Pipeline nicht
  (`changes:`-Filter, kein Frontend-Change).
* Ausgerollt auf der KI-Box (.140): `polyschnack-ps-webapp-1` neu erstellt,
  Label `org.opencontainers.image.revision=af8399ac`, API nach 3 s HTTP 200.

### Live-Abnahme (gemessen am ausgelieferten Stand)

* `GET /api/export/presets` → `fit_mode`: `{"type": "enum", "values": ["off",
  "balanced", "per_line"]}`; `safe_margin_pct`: `{"type": "int", "min": 0,
  "max": 20}`. Alle fünf Presets führen **beide** in `used_params`, die Regler
  erscheinen also im Dialog.
* Ausgeliefertes Bundle: `index-B_9IAANU.js`, 870 252 Bytes — identisch mit dem
  lokal gebauten; enthält `ass_pos_per_line` (3×), `ep_safe_margin_pct` (3×),
  `ass_warn_fit_tag_missing` (4×) und die Labels „Jede Zeile einzeln",
  „Sicherheitsrand (Safe Title)".
* Route/Auth: `/api/recordings/gibtsnicht/export/ass` → **HTTP 404** (Route da,
  Zugriffsprüfung greift).
* **Rechnung im ausgerollten Image** (`docker exec` im Webapp-Container,
  dieselbe Beispielaufnahme, `safe_margin_pct=5` → Ränder 96/96):

  | Modus | Zeilen | Größen |
  |---|---|---|
  | `per_line`, 1 Wort je Zeile | Ich, bin, ein, sehr, langes, Wort, Donau… | 830, 830, 830, 814, 543, 761, 78 px |
  | `per_line`, 4 Wörter je Zeile | „Ich bin ein sehr", „langes Wort Donau…" | 234, 61 px |
  | `off`, 4 Wörter je Zeile | dieselben Zeilen | kein `\fs`-Tag (Stil 48 px) |

  Damit ist der Sprung (Faktor ~11 zwischen kurzer und langer Zeile) am
  laufenden Container belegt, nicht nur an der Konfiguration.
