# Untertitel-Export: ASS-Datei und Video

Dieses Kapitel erklärt den Untertitel-Export — vom animierten Text zum
fertigen Video. Es richtet sich an Betreiber der Installation.

## Was der Export kann

PolySchnack erzeugt aus den Wort-Zeiten einer Aufnahme **animierte Untertitel**
(modern „Captions" oder „Karaoke-Untertitel" genannt): Das gerade gesprochene
Wort wird hervorgehoben, der Rest wird blass. Im Export-Dialog einer Aufnahme
(⬇️-Knopf → Zeile `ASS`) gibt es fünf fertige Stile — *Klassisch*, *Karaoke*,
*Hervorhebung*, *Kinetic*, *Modern* — sowie eigene Vorlagen.

Daraus gibt es zwei Wege:

1. **Die `.ass`-Datei herunterladen** — die Untertitel als Datei. Sie lässt sich
   in VLC anzeigen oder mit einem Videoprogramm selbst einbrennen.
2. **Ein Video erzeugen lassen** — die Untertitel landen fertig in einer
   Videodatei. Das läuft über den Dienst `ps-render`, der nur auf Wunsch läuft
   (siehe unten).

## Weg 1: die `.ass`-Datei

Der Dialog zeigt eine Vorschau („so sieht es aus"), erlaubt Farben, Schriftgröße,
Position und Zeilenlänge und lädt dann die Datei herunter. Der Server schickt
dabei im Hintergrund Warnhinweise mit (z. B. „die Wortzeiten wurden mechanisch
verteilt, bitte prüfen") — die Oberfläche zeigt sie an, statt sie zu verschlucken.

Voraussetzung sind **Wort-Zeiten**: Wurde die Aufnahme nur grob in Absätze
geteilt, kommt die Meldung „Für den Untertitel-Export werden Wort-Zeiten
gebraucht" und der Hinweis, zuerst auszurichten (Re-align).

## Weg 2: Video erzeugen (Dienst `ps-render`)

Weg 2 braucht den zusätzlichen Container `ps-render`. Er wird **nicht** mit dem
Rest gestartet, weil er viel Rechenzeit braucht und für viele Installationen
überflüssig ist.

### Die vier Formate

- **MP4 (Untertitel eingebrannt)** — ein fertiges Video, in dem die Untertitel
  fest hineingerechnet sind. Enthält die Aufnahme eine Tonspur, wird deren Ton
  mitgenommen; sonst wird ein einfarbiger Hintergrund erzeugt. Für YouTube,
  Social Media oder zum Verschicken.
- **WebM (nur Untertitel, transparent)** — ein Video, das **nur** aus den
  Untertiteln besteht; überall, wo kein Text steht, ist es durchsichtig. Man legt
  es im Schnittprogramm über sein eigenes Video. Kleine Datei, im Browser
  prüfbar.
- **MOV ProRes 4444 (nur Untertitel, transparent)** — dasselbe, aber im Format,
  das Schnittprogramme wie DaVinci Resolve oder Premiere von Haus aus erwarten.
  Deutlich größere Datei als WebM.
- **PNG-Sequenz als ZIP (nur Untertitel, transparent)** — jedes Einzelbild als
  PNG in einem Archiv. Für Programme, die kein Alpha-Video lesen können.
  Sehr große Datei.

### Was „transparent" (Alpha) bedeutet

Ein Bild besteht aus Farben — und einem vierten Wert pro Bildpunkt, der sagt, wie
**deckend** er ist: der Alphakanal. Ist er 0, ist der Bildpunkt durchsichtig. Die
drei Alpha-Formate liefern deshalb nur die Schrift: Man legt sie über das eigene
Filmmaterial, und die Untertitel sitzen sauber darüber, ohne dass ein schwarzer
Kasten oder ein farbiger Hintergrund das Bild zudeckt. Genau das ist der
Unterschied zu „eingebrannt", wo Hintergrund und Untertitel eine feste Einheit
sind.

### Dienst starten

Über die Compose-Datei, mit dem Profil `render`:

```bash
cd /opt/container/polyschnack
docker compose --profile render -f compose.yml -f compose.oidc.yml \
  -f compose.backends.yml -f compose.gpu.yml up -d ps-render
```

Der Dienst hört intern auf Port 8090; die Webapp erreicht ihn über das
Docker-Netz unter `http://ps-render:8090` (Umgebungsvariable `RENDER_URL`).
Nach außen wird nur `127.0.0.1:8091` veröffentlicht — für Handproben.

**Läuft der Dienst nicht**, bleibt alles andere wie es ist: Die API meldet
`render_available: false`, der Dialog zeigt keinen toten Knopf, sondern den
Hinweis, wie man die `.ass`-Datei selbst einbrennt.

### Grenzen und Ressourcen

- **Ein Auftrag gleichzeitig.** Rendern ist rechenintensiv; parallele Aufträge
  würden die Transkription ausbremsen. Weitere Aufträge warten in der Reihe.
- **4 CPU-Kerne, 2 GB Speicher** als Obergrenze (im Compose-Eintrag änderbar).
- **Höchstens 30 Minuten pro Auftrag**, danach bricht der Dienst ab.
- **Fertige Dateien werden nach 24 Stunden gelöscht.** Sie liegen in
  `./DATA/render`; wer sie länger braucht, lädt sie vorher herunter.
- **Kein GPU-Zugriff nötig** — die Formate (VP9-Alpha, ProRes 4444) haben keinen
  nutzbaren Hardware-Pfad.

### Fortschritt

Der Fortschrittsbalken kommt aus dem Rechenprogramm selbst, nicht aus einer
Schätzung. Solange noch kein Abschnitt fertig ist, steht dort „Der Dienst
rechnet …" statt einer erfundenen Prozentzahl. Abbrechen ist jederzeit möglich.


## Handy-Schnitt (KineMaster & Co.)

Auf dem Handy gelten andere Regeln als am Rechner — das ist der häufigste
Stolperstein beim Export.

**Welches Format liest KineMaster?** Laut Hersteller MP4/MOV/3GP mit H.264 oder
H.265 und AAC/PCM. Als einziges Format **mit Alphakanal** kann KineMaster seit
Version 7.1 **HEVC mit Alpha in einer MP4** lesen. WebM (VP9 mit Alpha),
MOV mit ProRes 4444 und die PNG-Sequenz stehen nicht auf dieser Liste.

**HEVC mit Alpha** wird geliefert — als Format „MP4 mit Alpha (HEVC)". Es
erscheint im Export-Dialog nur, wenn der Dienst es wirklich kann: Der Container
bringt dafür ein selbst gebautes ffmpeg mit (Ordner `ffalpha-build/`), und
`/health` meldet die Fähigkeit als `x265_alpha`. Fehlt sie, wird das Format
gar nicht erst angeboten, statt beim Export zu scheitern.

Warum der eigene Bau nötig ist — drei Dinge müssen zusammenkommen, jedes
einzeln nachgemessen:

1. **x265 mit `-DENABLE_ALPHA=ON` bauen.** Debian baut seine x265-Bibliothek
   ohne; die Option `alpha` ist dort nicht einmal registriert (Nachweis über
   die x265-Parameter-API: Debian lehnt sie ab, ein eigener Bau nimmt sie an).
2. **Die geteilte Bibliothek ins Prefix kopieren und `x265.pc` selbst
   schreiben.** x265s CMake installiert nur die statische Bibliothek, die
   Header und das Kommandozeilen-Werkzeug — eine pkg-config-Datei gibt es
   nicht, und ffmpeg findet die Bibliothek sonst nicht.
3. **ffmpeg aus Quellen mit Alpha-Code bauen** und beim Konfigurieren
   `-DX265_ENABLE_ALPHA` mitgeben. Version 7.1 enthält den Code nicht, ab 8.0
   ist er drin. Wichtig: Der Schalter wird an keiner Stelle automatisch gesetzt
   — deshalb hat auch ein Standardbau kein HEVC-Alpha.

Nachweis im Bau des Images: Die Formatliste des Encoders zeigt `yuva420p`, und
der Rundlauf (kodieren, wieder einlesen, Alpha extrahieren) liefert teils
transparente und teils deckende Bildpunkte. Ohne diesen Nachweis scheitert der
Image-Bau — ein Image ohne funktionierenden Alpha-Pfad ist wertlos.

Zum Nachlesen beim Suchen: `ffprobe` meldet die Spur als `yuv420p`, obwohl
Alpha drin ist — der Kanal liegt als eigene Ebene vor. Wer auf `pix_fmt` prüft,
sucht am falschen Ort; belastbar ist das Extrahieren des Alphakanals.

## Schriftart (Auswahlliste)

Die Schriftart ist ein **Auswahlfeld**, kein Textfeld: unbekannte Namen fielen
bisher still auf die Ersatzschrift von fontconfig zurück, der Export sah dann
anders aus als erwartet.

Angeboten wird nur, was **beide Seiten selbst auflösen** — die Webapp (dort wird
die Breite gemessen) und der Renderdienst (dort wird eingebrannt; er meldet
seine Schriften in ``/health`` als ``fonts``). Ein Name, den ein Host auf eine
andere Familie abbildet, erscheint nicht: sonst wäre die gemessene Breite
falsch. Deshalb fehlt z. B. ``Liberation Sans Narrow`` — es liegt nur im
Webapp-Image (``fonts-liberation`` 1.07.4 unter bookworm), das Render-Image
(2.1.5 unter trixie) zeigt dafür auf ``Liberation Sans``.

Angeboten werden die drei Standardnamen samt der Familie, auf die fontconfig sie
hier abbildet (metrik-gleich, deshalb ändert die Wahl die Größe nicht):

| Name | wird hier zu |
|---|---|
| ``Arial`` (Vorgabe) | Liberation Sans |
| ``Times New Roman`` | Liberation Serif |
| ``Courier New`` | Liberation Mono |

Ist der Renderdienst nicht erreichbar oder meldet er noch keine Liste, gilt die
Liste der messenden Instanz.

Die Auflösung ist **offen**: die API nimmt weiterhin jeden wohlgeformten Namen
an (Länge ≤ 64, Komma wird ersetzt, weil die ASS-Stilzeile komma-getrennt ist).
Die Liste ist eine Hilfe in der Oberfläche, keine Sperre — für Skripte und für
Untertitel, die in einem anderen Schnittprogramm weiterverwendet werden.

## Schriftgröße füllt die Bildschirmbreite (`fit_mode`)

Standardmäßig haben Untertitel eine **feste Schriftgröße** (`font_size`) und
brechen nach fester Wortzahl (`words_per_line`). Auf dem Bildschirm bleibt
dadurch oft Breite ungenutzt: vier kurze Wörter füllen bei 1920 px vielleicht
ein Drittel, obwohl Platz für deutlich größere Schrift wäre.

Der Parameter **„Schrift an die Bildbreite anpassen"** (`fit_mode`) schaltet das um:

* **`off`** (Vorgabe) — alles wie bisher: feste Größe, feste Wortzahl.
* **`balanced`** — die Zeilen werden nach **Breite** ausbalanciert und daraus
  **eine** Schriftgröße für den ganzen Export berechnet, die die breiteste
  Zeile ausfüllt. `words_per_line` bleibt als Obergrenze erhalten: es bestimmt,
  wie viele Wörter höchstens in eine Zeile dürfen. Harte Grenzen bleiben
  bestehen — Sprecherwechsel, Abschnittswechsel und (wenn eingeschaltet) das
  Satzende trennen weiterhin.
* **`per_line`** — die Zeilenbildung bleibt bei der eingestellten Wortzahl, und
  **jede Zeile bekommt ihre eigene Schriftgröße**: ein Wort riesig, zehn Wörter
  kleiner. Die Größe **springt** also von Anzeige zu Anzeige — das Aussehen der
  „Full-Screen"-Untertitel in sozialen Netzen. Mit `words_per_line=1` springt
  sie bei jedem Wort.

## Schriftgröße je Zeile (`fit_mode=per_line`)

Die Größe einer Zeile wird aus **zwei** Messungen bestimmt; die kleinere gewinnt:

* **Breite:** `verfügbare Breite / Zeilenbreite × Referenzgröße`. Maßgeblich ist
  die *Vorschubbreite* (advance width), nicht die Tinte: läuft der Vorschub über
  den Rand, bricht libass die Zeile um und die Caption steht zweizeilig im Bild.
  Deshalb erreicht die sichtbare Tinte etwa 88–95 % der Zeile — die letzten
  Prozentpunkte sind Seitenrand der Buchstaben und Abrundung.
* **Höhe:** die Zeile muss zwischen `margin_v` (unten) und dem oberen
  Sicherheitsrand Platz haben. Begrenzt wird auf die **Zeilenbox** (Auf- +
  Abstieg ≈ 1,14 em bei Liberation Sans), nicht auf die Tinte. Der Unterschied
  ist nicht theoretisch: ein Wort wie „ist" hat nur 0,78 em Tinte, die
  reservierte Box ist trotzdem 1,14 em hoch — mit der Tinte als Grenze wurde die
  Zeile im Test oben abgeschnitten. Ohne Höhengrenze bekäme ein einzelnes kurzes
  Wort eine Schriftgröße von weit über 1000 px und liefe aus dem Bild.

Anders als bei `balanced` gibt es hier **keinen** Deckel auf 3 × `font_size`:
der Sprung ist ja das Ziel. Die eingestellte `font_size` wirkt als Untergrenze
(Richtung) und bleibt im ASS-Stil stehen; jede Zeile trägt zusätzlich ihr eigenes
`{\fs…}` im Event-Text. Zu klein wird nichts: die Untergrenze ist
`max(8 px, 0,5 × font_size)`.

## Sicherheitsrand (`safe_margin_pct`)

Der Rand in Prozent **je Seite** (Vorgabe 5, einstellbar 0–20) hält die Schrift
von den Bildrändern fern:

* **waagerecht** — `MarginL`/`MarginR` des ASS-Stils werden
  `max(40 px, pct % von play_res_x)`. Bei 1920 px und 5 % sind das 96 px je
  Seite; derselbe Wert geht in die Schriftberechnung ein (eine Wahrheit, nicht
  zwei).
* **senkrecht** — der obere Sicherheitsrand (`pct % von play_res_y`) begrenzt die
  Zeilenbox.

Der Rand wirkt in **allen** Modi, auch bei `off` — er ist eine Eigenschaft des
Bildes, nicht der Schriftanpassung. `0` stellt den Stand vor Change 202 exakt
wieder her (40 px Ränder). Mit der Vorgabe 5 % wird auch `balanced` etwas
kleiner als früher, weil die Ränder jetzt wirken (verfügbare Breite bei 1920 px:
1833 → 1721 px).

## Eigene Vorlagen und die Größe je Zeile

Die Größe je Zeile kann nicht im ASS-**Stil** stehen (der gilt für alle Events),
sondern nur im Event-Text. Deshalb bekommen Vorlagen zwei neue Variablen:

* `{{ line.fs_tag }}` — z. B. `{\fs108}`, bei `off`/`balanced` leer
* `{{ st.fs_tag }}` — dasselbe für die Wort-Schritte (Presets „Aufpoppen" und
  „Social Media")

Die mitgelieferten Vorlagen setzen den Tag an den Anfang des Text-Feldes. Eine
eigene Vorlage **ohne** diesen Platzhalter wird nicht stillschweigend ohne
Wirkung exportiert: der Export meldet, dass die Vorlage die berechnete Größe
nicht übernimmt, und der Text bleibt in der Stilgröße.

### Gemessen, nicht geschätzt

Die Breite wird mit der Schrift gemessen, die der Renderer auch benutzt:
`fc-match` löst den Namen auf (Arial → Liberation Sans, wie im Render-Container),
gerastert wird über FreeType. Großschreibung (`uppercase`), fette Schrift, die
seitlichen Ränder des Stils und ein Zuschlag für Kontur und Schatten gehen in
die Rechnung ein. Die verfügbare Breite ist

```
play_res_x − margin_l − margin_r − 2 × outline_width − schatten
```

### Grenzen und Meldungen

* Die berechnete Größe wird auf **0,5× bis 3× der eingestellten `font_size`**
  begrenzt — die eingestellte Größe gibt also die Richtung vor. Sehr kurze
  Zeilen füllen deshalb nicht die gesamte Breite: wer größere Untertitel will,
  stellt `font_size` höher und lässt `balanced` den Rest machen.
* Passt eine Zeile selbst bei der Untergrenze nicht (etwa ein sehr langes
  Einzelwort), wird sie **gemeldet**: „In n Zeile(n) passt der Text auch mit der
  kleinsten Schrift nicht in die Breite." Es wird nichts stillschweigend über
  den Rand geschrieben.
* Kann das Image die Schrift nicht messen (Pillow oder Schriften fehlen),
  wird der Regler **gar nicht erst angeboten** — ein Regler ohne Wirkung im
  Dialog ist schlimmer als kein Regler (dieselbe Regel wie beim Render-Dienst,
  der Formate ohne Encoder nicht anbietet). Wer den Modus trotzdem über die API
  anfordert, bekommt die Warnung „Textbreite ließ sich nicht messen" und die
  eingestellte Größe unverändert. Der Image-Bau prüft die Fähigkeit, damit das
  nicht erst im Betrieb auffällt.

### Praxiserfahrung

An einer Aufnahme mit gemischten Satzlängen, gemessen über die ganze Aufnahme
(breiteste Zeile entscheidet, weil eine gemeinsame Größe gilt):

| | feste Größe (`off`) | `balanced` |
|---|---|---|
| Schriftgröße im ASS | 56 px | 108 px |
| breiteste Zeile im Video | 559 px = 46 % der Breite | 1079 px = 88 % |
| Zeilen im Testbeispiel | 728–942 px | 1236–1816 px |

Die Zeilen *innerhalb* eines Satzes werden gleichmäßig; zwischen Sätzen können
die Breiten abweichen, weil das Satzende eine harte Grenze bleibt. Die letzten
Prozente bis zur vollen Breite bleiben absichtlich frei: der Zuschlag für Kontur
und Schatten, die Abrundung auf ganze Pixel und der Unterschied zwischen
Vorschubbreite (gemessen) und tatsächlicher Tintenbreite (gerendert).


### Praxiserfahrung `per_line` (gemessen)

Beispielaufnahme mit einem Wort, kurzen Wörtern und einem Wortungeheuer
(1920 × 1080, `safe_margin_pct=5`, Ränder 96 px → 1721 px verfügbar):

| Zeile | `per_line` |
|---|---|
| „Ich" (1 Wort) | 830 px |
| „langes" | 543 px |
| „eines Donaudampfschifffahrtsgesellschaftskapitaen" | 69 px |
| vier Wörter je Zeile: „Ich bin ein sehr" | 234 px |
| vier Wörter je Zeile: „langes Wort und noch" | 164 px |

Die Ein-Wort-Zeile ist also rund zwölfmal so groß wie die längste Zeile — genau
der Sprung, den der Modus erzeugt. Bei einer Größe von 830 px füllt die
Zeilenbox (1,14 em = 946 px) den Platz zwischen `margin_v` und oberem
Sicherheitsrand aus; weiter geht es physikalisch nicht, ohne oben abzuschneiden.

**Was auf dem Handy funktioniert:**

- **MP4 mit eingebrannten Untertiteln** (`burn_mp4`) — das fertige Video mit
  Text im Bild. Läuft überall, kein Alpha nötig.
- **MP4 auf schwarzem Grund mit Mischmodus „Screen"** (`screen_mp4`) — im
  Schnittprogramm als Ebene einfügen und den Mischmodus auf *Screen* stellen:
  Der schwarze Grund verschwindet, es bleibt nur die Schrift. KineMaster hat
  24 Mischmodi und beschreibt dieses Vorgehen selbst; ohne Chroma-Key-Fransen.
- **MP4 auf grünem Grund mit Chroma Key** (`chroma_mp4`) — für Programme, die
  kein „Screen" können. Die Farbe ist einstellbar (Standard `#00B140`).

Am Rechner (DaVinci Resolve, Premiere) sind dagegen `alpha_webm`, `alpha_mov`
und `alpha_png` die richtige Wahl — dort ist echter Alphakanal verfügbar.

## Wenn etwas nicht klappt

- **„Video-Rendern ist auf dieser Installation nicht aktiviert"** — Der Dienst
  läuft nicht. Entweder starten (siehe oben) oder die `.ass`-Datei
  herunterladen. In Klammern nennt die Meldung den technischen Grund, z. B.
  `ConnectError`.
- **Ein Format fehlt in der Auswahl** — Das Image des Dienstes enthält den
  nötigen Encoder nicht. Ein Format, das die Installation nicht kann, wird gar
  nicht erst angeboten. Der Dienst meldet den Stand unter `GET /health`.
- **Schrift sieht anders aus als erwartet** — Die Stile nennen „Arial"; Arial
  darf nicht mitgeliefert werden. Im Image liegt deshalb die maßgleiche
  *Liberation Sans*, und eine Regel in `fontconfig` bildet Arial darauf ab.
  Welche Schrift wirklich benutzt wird, steht in `/health` unter `font_arial`.
- **Zu große Datei** — Die Untertiteldatei darf 2 MB haben, die Tonspur 2 GB.
  Bei sehr langen Aufnahmen ist WebM statt ProRes die deutlich kleinere Wahl.
- **Datei ist weg** — nach 24 Stunden räumt der Dienst auf. Neu erzeugen.

## Für den Betrieb: Kurzreferenz

| Einstellung | Bedeutung |
| --- | --- |
| `RENDER_URL` (Webapp) | Adresse des Dienstes, Standard `http://ps-render:8090` |
| `RENDER_DATA` | Arbeitsverzeichnis im Dienst, Standard `/data/render` |
| `RENDER_TTL_S` | Aufbewahrung fertiger Dateien in Sekunden, Standard 86400 (24 h) |
| `RENDER_TIMEOUT_S` | Obergrenze pro Auftrag in Sekunden, Standard 1800 (30 min) |
| `RENDER_PORT` (Host) | Nur für Handproben, Standard 8091 auf 127.0.0.1 |