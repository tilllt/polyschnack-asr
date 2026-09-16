# Change 199 — Detailwellenform fürs Wort-Timing

**Status:** in Arbeit
**Betroffen:** `app/peaks.py`, `app/routers/recordings.py`, `app/models.py`,
`frontend/src/components/WaveformPlayer.tsx`, `frontend/src/waveformTime.ts`,
`frontend/src/api.ts`

## Problem

Im Timing-Modus zeigt die Wellenform beim Wort-Zoom nur noch senkrechte
Striche — man kann daran keine Wortgrenze beurteilen. Drei unabhängige
Ursachen, alle gemessen an der gemeldeten 262-Minuten-Aufnahme
(`b68d6e39…`, `duration_s = 15718`, WAV 502.963.544 B, Preview 46.949.384 B):

### 1. Die Peaks-Auflösung fällt mit der Aufnahmelänge

Der Peaks-Endpunkt liefert ein **festes Envelope über die ganze Datei**:
`?length=N` verteilt N Bins gleichmäßig über die Gesamtlänge. Die Auflösung
pro Sekunde ist damit `N / Dauer` und sinkt, je länger die Aufnahme ist.

| | |
|---|---|
| Aufnahmelänge | 262 min (15.718 s) |
| Bins bei `?length=300000` (Server-Maximum, `le=300000`) | 300.000 |
| → Auflösung | **19,1 Bins/s = 52,4 ms pro Bin** |
| Antwortgröße / Rechenzeit | 5.997.910 B / 3,23 s |

Was der Wort-Zoom davon bei 1000 px Breite sieht:

| Wortlänge | pps | sichtbares Fenster | Bins im Fenster | px pro Bin |
|---|---|---|---|---|
| 0,1 s | 3000 | 0,33 s | **6,4** | 157 |
| 0,2 s | 1500 | 0,67 s | 12,7 | 79 |
| 0,3 s | 1000 | 1,00 s | 19,1 | 52 |
| 1,0 s | 300 | 3,33 s | 63,6 | 16 |

Bei einem 0,1-s-Wort werden **6 Balken über 1000 px** gezeichnet. Das sind
die „Linien". Der Frontend-Code fordert mit `Math.min(300000, …)` bereits
das Server-Maximum an — es ist keine Einstellung, die man hochdrehen könnte.

### 2. Jede Anfrage dekodiert die ganze Datei neu

`GET /recordings/{rid}/peaks?length=N` ruft
`compute_peaks_path(src, n_bins=length)` auf — ein **voller ffmpeg-Dekodierlauf
über die komplette Datei**, bei jedem einzelnen Zoom-Wechsel. Gemessen:
3,23 s für 262 min. Die Berechnung ist rein von der Dateilänge abhängig,
nicht vom angefragten Zoom.

### 3. Die Browser-Breitengrenze deckelt den Zoom

WaveSurfer setzt die Gesamtbreite auf `Dauer × px/s`. Der Browser deckelt
Elementbreiten bei **2^25 = 33.554.428 px** (gemessen: 1 Mrd. px angefordert,
33.554.428 px zurückgegeben). Daraus folgt `px/s ≤ 33.554.428 / Dauer`:

| Datei | effektiver Maximalzoom |
|---|---|
| 10 min | 55.900 px/s → `MAX_TIMING_PPS` = 48000 greift |
| 11,7 min | 48.000 px/s (Grenze) |
| 1 h | 9.320 px/s |
| **262 min** | **2.135 px/s** |

`MAX_TIMING_PPS = 48000` (Change 197) ist damit für alles über ~11,7 Minuten
unerreichbar. Folge: die Invariante aus Change 197 („ein Wort muss sein
30-%-Zielfenster erreichen") kann bei kurzen Wörtern auf langen Dateien
nicht gelten — ein 0,1-s-Wort sind bei 2135 px/s nur 213 px statt 300.

## Ursache

Zwei Design-Entscheidungen, die einzeln richtig waren und zusammen nicht
skalieren:

1. **Ein uniformes Envelope über die ganze Datei.** WaveSurfer bildet
   Array-Index linear auf Zeit ab (`createBuffer(peaks, duration)`), und der
   Renderer zeichnet `(Chunkbreite / Gesamtbreite) × N` Werte über die
   Chunkbreite. Daraus folgt zwingend **Bins/s ≥ px/s**: mehr Detail als
   Array-Länge kann der Renderer nicht zeigen. Ein ganzer 4-Stunden-Datei
   bräuchte bei Wort-Zoom 15,7 Mio. Bins — als Float32Array 63 MB.
2. **Die Auflösung wird bei der Anfrage erzeugt statt beim Import.** Detail
   kostet dadurch bei jedem Klick einen vollen Dekodierlauf.

## Lösung

### A) Sidecar beim Import statt Dekodieren bei der Anfrage

Der bestehende Peaks-Job (`_compute_peaks_background`) **dekodiert die Datei
bereits vollständig**. Er schreibt künftig zwei binäre Sidecars daneben — aus
demselben Dekodierlauf, also **ohne zusätzlichen ffmpeg-Aufwand**:

| Datei | Inhalt | Auflösung |
|---|---|---|
| `<stem>_peaks_hi.bin` | Detail-Envelope, uint8 | **1000 Bins/s** (1 ms) |
| `<stem>_peaks_res.bin` | residentes Envelope, uint8 | `min(1000, 2 Mio. / Dauer)` |

Datenfluss: **ein** Dekodierlauf füllt das 1000-Bins/s-Envelope; das
residente Level und das bisherige 2000-Punkte-JSON werden daraus per
Max-Pooling abgeleitet (`np.maximum.reduceat`).

uint8 (256 Stufen) reicht: die Wellenform wird 128 px hoch gezeichnet.
Bestehende Aufnahmen bekommen die Sidecars über den vorhandenen
`_backfill_peaks_batch`-Pfad nachgezogen.

### B) Zwei Endpunkte, Binary, Range-fähig

```
GET /api/recordings/{rid}/peaks.bin?level=res   → residentes Envelope
GET /api/recordings/{rid}/peaks.bin?level=hi    → Detail-Envelope (Range)
```

Beide als `FileResponse` (Range-Unterstützung inklusive — am Audio-Endpunkt
verifiziert: `206` mit `content-range: bytes 0-1023/46949384`). Das residente
Level ist mit ≤ 2 MB klein genug für den vollen Abruf, das Detail-Level wird
per `Range` fensterweise angeschnitten. Kein ffmpeg zur Anfragezeit.

### C) Residentes Level über ein Speicherbudget statt über 2000 Punkte

`bins/s = min(1000, BUDGET / Dauer)` mit `BUDGET = 2.097.152 Bins` (2 MB
uint8). Daraus folgt eine von der Dateilänge **unabhängige** Eigenschaft:

```
Balken im Maximalzoom = BUDGET × Fensterbreite / 2^25
                      = 2.097.152 × 1000 / 33.554.428 ≈ 62
```

Weil sich `Dauer` herauskürzt, liefert das Budget auf jeder langen Datei
gleich viele Balken (62 bei 1000 px). Das ist der Vorteil gegenüber dem
heutigen 300.000er-Deckel, der mit der Dateilänge verfällt.

| Datei | bins/s | Nutzlast | Balken @ Maximalzoom |
|---|---|---|---|
| 262 min | 133 | 2,0 MB | 62 |
| 1 h | 582 | 2,0 MB | 62 |
| 10 min | 1000 | 0,6 MB | 235 |

Zum Vergleich: heute lädt der Wort-Zoom **6 MB JSON** für 19 Bins/s.

### D) Detail-Canvas nur im Pausenzustand

Beim Abspielen ist Detail nicht nötig (Entscheidung des Users). Deshalb:

* **Während des Abspielens:** keine Anfragen, keine Detaildaten. Gezeichnet
  wird das residente Envelope aus dem Speicher — wie heute, nur mit 62 statt
  9 Balken im Fenster.
* **Pausiert im Timing-Modus:** ein Overlay-Canvas zeichnet das Detailfenster
  aus der `hi`-Sidecar, 1 Bin pro Pixel, Fenster = sichtbarer Bereich ± 50 %.
  Bei 1 s Fenster und 1000 Bins/s sind das **~1–2 KB pro Anfrage**.

Damit entfällt die gesamte Nachlade-Maschinerie fürs Playback: kein
Prefetch-Vorlauf, keine Regel „`slice()` darf nie warten", weil während des
Abspielens nie gefetcht wird.

WaveSurfer behält Playback, Scroll, Regionen und Playhead unverändert. Das
Detail ist rein additiv — **kein Eingriff in WaveSurfer-Interna**, was die
Lösung gegen WS-Upgrades robust hält (vgl. die erwogene WS8-Migration).

### E) Enhance-Blende

Der Wechsel vom residenten zum detaillierten Envelope beim Pausieren wird
animiert — im Stil der „können wir das schärfer haben"-Szene: kurzes
Pixelrauschen, dann scharf. ~320 ms, zwei Phasen:

1. **0–120 ms „Rauschen":** grobe Form mit Körnung überschichtet, leichte
   horizontale Unruhe.
2. **120–320 ms „scharf":** die Detailwellenform löst sich auf, Körnung
   blendet aus, ein Scan-Band läuft durch.

Regeln: läuft nur beim Übergang grob → fein (also beim Pausieren), nicht bei
jedem Repaint; `prefers-reduced-motion: reduce` überspringt die Animation und
setzt direkt das scharfe Bild. Reines Canvas-Rauschen, keine CSS-Filter — die
App hat bereits einen `prefers-reduced-motion`-Respekt im Skill-Guide.

## Was bewusst NICHT in diesem Change steckt

* **Kein Eingriff in WaveSurfer-Interna** (kein eigenes `audioData`, kein
  Proxy für das Peaks-Array). Begründung: `createBuffer` materialisiert das
  Array eager (`Float32Array.from`) und scannt es mit `.some()` — ein lazy
  Objekt überlebt das nicht. Ein Umweg über Interna wäre upgrade-fragil.
* **Kein Detail während des Abspielens** (User-Entscheidung).
* **Keine eigene Zeitachsen-Übersetzung** (Variante: WS hält die Datei für
  kurz und wir rechnen um). Würde Timeline, Seek, Fortschritt und Regionen
  gleichzeitig umbauen — nicht verhältnismäßig.
* **Kein AbortController** für das residente Envelope (Change 198 hat den
  Korruptionspfad geschlossen; ein abgebrochener Download ist verschwendete
  Bandbreite, kein Korruptionsrisiko).

## Risiken

* **Speicherbedarf pro Aufnahme:** 1000 Bins/s sind bei 262 min 15,7 MB plus
  2 MB resident. Gegen 503 MB WAV vertretbar, aber der Gesamtbestand wächst
  um ~3 % der Audiodaten. Vor dem Backfill wird die Korpusgröße gemessen.
* **Der Nachlauf dekodiert jede Bestandsdatei einmal neu** (~21 s pro Stunde
  Audio, hochgerechnet aus gemessen 5,89 s für 17 min). Läuft im vorhandenen
  Backfill-Pfad mit begrenzter Batch-Größe, also nicht in der Request-Zeit.
* **Der sichtbare Wechsel** grob ↔ fein beim Play/Pause bleibt bestehen — er
  ist die bewusste Konsequenz der Aufteilung und wird durch die Blende
  gerahmt statt versteckt.
* **Die Breitengrenze bleibt.** Sie gehört zur Zoom-Mechanik, nicht zur
  Datenquelle. Die Change-197-Invariante wird an die echte Obergrenze
  angepasst (`min(MAX_TIMING_PPS, 2^25 / Dauer)`), sonst steht eine
  Zusicherung im Code, die der Browser nicht einhalten kann.

## Verifikation

* Backend: Sidecar-Länge == `round(Dauer × 1000)`; Max-Pooling aus dem
  Hi-Level reproduziert das 2000er-JSON; Range-Request liefert `206` mit
  korrektem `content-range`; Auflösungsformel (`bins/s`) gegen Dauer.
* Frontend: Budget-Funktion (`bins/s = min(1000, BUDGET/Dauer)`) und die
  invariante Balkenzahl `BUDGET × Breite / 2^25`; Detailfenster-Berechnung;
  Blenden-Zustandsmaschine inkl. `prefers-reduced-motion`-Pfad.
* Live: an `b68d6e39…` messen — Sidecar-Größe, Übertragung pro Detailfenster
  (Ziel ~1–2 KB), Balken pro 1000 px im Wort-Zoom (Ziel: ≥ 300 statt 6),
  kein ffmpeg-Lauf mehr im Serverlog bei einem Zoom-Wechsel.
