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
