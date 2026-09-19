# Change 210 — Timing-Tab: Bedienbarkeit und Sichtbarkeit

**Nutzer-Befunde 19.09.2026 (wörtlich):**

> „Bei einer längeren Transkription kann ich nur die ersten drei Zeilen von Wörtern clicken
> (ca 20-30 wörter). Bei den anderen passiert nichts. Die Markierungen der Range und des Wortes davor
> und danach sind nicht deutlich genug zu sehen. Können wir die kante die man gegriffen hat
> highlighten?"

> „Wenn man auf das Timing Tab geht und du den process button ausblendet, danach geht man zurück zu
> transcription, fehlt der process button immer noch."

## Was geprüft wurde (und was nicht die Ursache ist)

- **Daten sind in Ordnung:** In allen 96 fertigen Aufnahmen der Produktion haben die Wörter durchgehend
  Wort-Zeitstempel — auch im letzten Segment der längsten Aufnahme (1544 Segmente, 41 546 Wörter,
  0 Wörter ohne Zeiten). Ein fehlender Wort-Zeitstempel als Ursache ist damit ausgeschlossen.
- **Nicht reproduzierbar von hier:** Der Dienst liegt hinter OIDC (kein gespeicherter Login im Tresor),
  und der virtualisierte Listen-Pfad lässt sich in jsdom nicht abbilden (clientHeight 0 → die Liste
  rendert dann alle Zeilen; ein Rect-Stub bringt den Virtueller nicht zuverlässig in den Fenster-Modus).
  Ein entsprechender Test wurde deshalb **wieder entfernt** statt als wackliger Test stehen zu bleiben.
- **Nicht bestätigt, aber plausibel und adressiert** — drei Ursachen, die „Klick tut nichts" erzeugen:

## Was geändert wurde

### 1. Wortliste: 260 px → 62 vh (Timing-Tab)

`SegmentList` bekommt `tall` (neuer Modus) → im Timing-Tab `max-h-[62vh]` statt `max-h-[260px]`.
Vorher war der Kasten ~fünf Zeilen hoch; der Rest musste im engen Kasten gescrollt werden — genau
die gemeldeten „ersten drei Zeilen". Im Edit-Vollbild (`listFillHeight`) füllt die Liste weiterhin
die verfügbare Höhe.

### 2. Kein stiller Leerlauf mehr

`handleTimingWordSelect` kehrte bei einem Wort ohne eigene Zeiten **stumm** zurück (User-Regel:
stille Fehler sind inakzeptabel). Jetzt erscheint ein Hinweis
(`timing_word_no_time`: „Dieses Wort hat keine eigene Zeit — bitte die Aufnahme neu ausrichten").

### 3. Waveform in den Blick holen

Beim Laden eines Wortes scrollt die Waveform jetzt ins Sichtfeld (`scrollIntoView`, block:
„nearest"). Ohne das entstanden Zoom und Markierung außerhalb des Sichtfelds — optisch „passiert
nichts", obwohl die Auswahl funktioniert.

### 4. Marker deutlich sichtbar + Beschriftung + Legende

- Aktives Wort: kräftigeres Grün (`rgba(46,160,67,0.30)`) **plus 2 px Rahmen**.
- Nachbar-Marker: **Bernstein** (`rgba(210,153,34,0.20)`), **gestrichelter Rahmen** und die
  Beschriftung „davor" / „danach" direkt am Marker.
- Kopfzeile im Timing-Tab: **Farblegende** (Farbfeld + Text) für „aktives Wort" und
  „Nachbar (schrumpft mit)".

### 5. Gegriffene Kante hervorheben

Beim Ziehen setzt der Player am Region-Element die Klasse `ps-edge-start` bzw. `ps-edge-end`
(WaveSurfer liefert die Seite im `update`-Event). Die CSS-Regeln machen den **Handle dicker,
grün und leuchtend** und ziehen einen Saum um die Markierung. Beim Loslassen (`update-end`) wird die
Hervorhebung entfernt. Klassennamen des Handles wurden gegen die installierte Version geprüft
(wavesurfer.js **7.12.11**: `region-handle-left` / `region-handle-right`).

### 6. Start-Knopf bleibt sichtbar (Folgefehler aus Change 208)

Der ganze Start-Block wurde im Timing-Tab **nicht gerendert** — nach dem Zurückwechseln wirkte er
dadurch „verschwunden". Jetzt bleibt die Zeile immer da; im Timing-Tab ist der Knopf **deaktiviert**
(`disabled` + `data-timing-disabled="true"` + Titel „Im Timing-Modus nicht bedienbar — erst zurück
zur Transkription."). Das erfüllt die ursprüngliche Vorgabe („ausgeblendet ODER nicht klickbar"),
kann nicht mit Play verwechselt werden und macht einen Layout-Sprung unmöglich.

## Nachweis (Tests)

- `TimingEditor.height.test.tsx` (neu, 3 Tests): Liste nutzt `max-h-[62vh]` (nicht mehr 260 px),
  Farblegende vorhanden (grün + bernstein), im Vollbild `fillHeight`.
- `RecordingCard.test.tsx` (angepasst): Start-Knopf im Transkriptions-Tab sichtbar **und bedienbar**,
  im Timing-Tab sichtbar aber **deaktiviert** mit Titel, nach dem Zurückwechseln wieder bedienbar.
- `tsc --noEmit` sauber; volle Frontend-Suite grün.

## Offen

- **Gegenprobe am Gerät:** Klick auf ein Wort weit unten in einer langen Transkription. Bleibt es
  wirkungslos, liefert der neue Hinweis (oder dessen Ausbleiben) die entscheidende Information:
  Kommt ein Hinweis → das Wort hat keine Zeit; kommt keiner und die Waveform zoomt → die Ansicht war
  nur weggescrollt.
- Der virtualisierte Listen-Pfad bleibt in jsdom untestbar (dokumentiert oben).
