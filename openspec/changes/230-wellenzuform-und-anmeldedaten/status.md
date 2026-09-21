# Change 230 — Wellenform im Hintergrund zeichnet nicht / Anmeldedaten überdecken die Kreis-Beschriftung

Nutzer-Befunde 21.09.2026, wörtlich:

> - recording: die waveform im background während des recordings baut sich nicht auf.
> - download: die credentials option ragt in das "download" label des buttons. es ist aber auch noch platz bis zur unteren begrezung der drop area, sie kann tiefer.

## Befund 1 — Wellenform: Ursache im eigenen CSS (bewiesen)

Vorgehen: lokale Oberfläche (Vite, `127.0.0.1:5199`) mit **synthetischem Mikrofon**
(`AudioContext` + `MediaStreamDestination`, im Test als nicht stumm nachgewiesen:
Spitze 0,300) und echtem Aufnahmelauf.

Messungen:

- Im DOM entstanden während der Aufnahme **0 Leinwände** (`document.createElement('canvas')`
  wurde nie gerufen), das Bild der Zone war leer — kein Sichtbarkeitsproblem, es wurde nie gezeichnet.
- Der Baustein **rief** `load()` auf (80 Aufrufe in 4 s, Argumente gültig: 1024 Werte,
  Dauer 10,24 s) — der Aufruf kam also an, blieb aber folgenlos.
- WaveSurfer isoliert (eigener Behälter, gleiche Optionskombination) zeigte den Unterschied:

  | Behälter-CSS | `getWidth()` | Leinwände |
  |---|---|---|
  | ohne Flex | 636 px | 2 |
  | `display:flex; align-items:center; justify-content:center` | **1 px** | **0** |
  | `display:flex; align-items:center` | 1 px | 0 |
  | `position:absolute; inset:0` | 636 px | 2 |

**Ursache:** `.ps-record-wave` trug `display:flex; align-items:center;
justify-content:center` (Rest der früheren 60-px-Band-Darstellung). WaveSurfer legt seine
Zeichenfläche als Kind in diesen Behälter; als Flex-Element mit `align-items:center`
schrumpft sie auf 1 px Breite → keine Zeichenfläche, nichts wird gezeichnet.

**Änderung:** Die drei Flex-Eigenschaften entfallen. Gemessen danach im echten
Aufnahmelauf: 2 Leinwände 636 × 208 px, 424 von 636 Spalten mit Tinte (= Balkenmuster
über die volle Breite), Deckkraft 0,35, im Bild sichtbar.

## Befund 2 — Anmeldedaten überdecken die Beschriftung „Download"

Gemessen am lebenden System:

- Desktop (Zone 212 px): Beschriftung endet bei 423,8 px, Rahmen der Anmeldedaten begann
  bei 403,8 px → **20 px Überdeckung**, darunter **32,1 px** freier Platz.
- Mobil (Zone 192 px): 15 px Überdeckung, 28 px Platz bis zum Zonenende.

**Änderung:** `.ps-zone-url > .ps-zone-auth` wandert 22 px nach unten
(`margin-top: 22px`) — der negative Außenabstand unten (`margin-bottom: -22px`) hebt die
Höhenzunahme wieder auf, sonst zentriert die Zone ihren Inhalt neu und URL-Zeile samt
Kreis rutschen um 11 px nach oben. Die Regel „der Kreis steht fest" (Change 223) bleibt
damit gewahrt.

## Offen / ehrlich benannt

- Die Welle ist jetzt sichtbar und füllt die Zone; ob sie **sichtbar von links nach
  links wächst**, konnte ich mit dem synthetischen Ton nicht abschließend belegen — in
  meiner Messung war die Fläche schon nach 2,5 s über die volle Breite mit Balken belegt
  (Tintenhöhe je Achtel konstant). Das entscheidet der Blick am echten Mikrofon.
- Der Prüflauf wurde mit einem **synthetischen** Mikrofon gemacht (der Automations-Browser
  hat kein echtes). Aufnahme, Pausen, Upload wurden nicht verändert.

## Belege

- `frontend/src/index.css` — `.ps-record-wave` (ohne Flex), `.ps-zone-url > .ps-zone-auth`.
- Messungen: lokaler Aufnahmelauf, WaveSurfer-Einzelprobe in vier Behältervarianten.
- Tor: tsc 0, 602 Frontend-Tests grün, Bau durch.
