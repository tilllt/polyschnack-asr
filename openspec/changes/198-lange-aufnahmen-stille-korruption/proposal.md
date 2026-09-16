# Change 198 — Lange Aufnahmen: stiller Korruptionspfad beim Audio-Laden

## Symptom

Nutzer-Befund: „Bei langen Audio-Files und schlechter/langsamer Netzverbindung
zeigt WaveSurfer nach einer Weile Waveform/Audio corrupt."
Beispiel: `https://whisper.cia-spandau.de/r/b68d6e39b5d548798600392c7ced39a2`

**Keine Fehlermeldung** — die Welle sieht nur falsch aus und das Audio endet früh.

## Gemessene Ausgangslage (dieser Share)

| | |
|---|---|
| Aufnahmelänge | **262,0 min = 4 h 22 min** (`duration_s = 15718`) |
| Preview `/audio/preview` | **46,9 MB** (`content-length: 46949384`, `accept-ranges: bytes`) |
| Original `/audio` | **503,0 MB** (WAV, 16 kHz mono 16-bit) |
| Backend laut `resolveBackend()` | **MediaElement** (> 30 min) |

> **Korrektur zur ersten Fassung:** Dort stand „97,8 min (MP3 64 kbps)". Das war
> aus der Dateigröße bei angenommener 64-kbps-Bitrate hochgerechnet und falsch.
> Die echte Länge belegen zwei unabhängige Quellen: die App-Metadaten
> (`262m 6s`) und die WAV-Größe (502.963.544 B ÷ 32.000 B/s = 15.717 s).
> Der gemessene `decodeAudioData`-Wert im Browser bestätigt sie
> (`duration_s: 15718`). Die Preview ist damit ~24 kbps, nicht 64.
> Für die Timeout-Rechnung ändert das nichts — die hängt nur an der Dateigröße.
> Der Commit-Titel von `c64b839` nennt noch „98 min"; die Historie wird dafür
> nicht umgeschrieben.

## Ursachenkette (jede Stufe belegt)

### 1. Der Worker-Pfad ignoriert den Backend-Modus

`WaveformPlayer.tsx` wählt ab 30 min korrekt `MediaElement`, damit lange
Aufnahmen **streamen** statt komplett geladen zu werden (Change 112 —
Begründung war OOM auf Android). Der Worker-Pfad prüft das aber nicht:

```js
if (typeof Worker !== "undefined" && audioUrl) {   // ← kein backend-Check
  workerFetch(audioUrl, …)
```

Damit lädt der Worker im MediaElement-Modus **trotzdem die vollen 47 MB**,
dekodiert sie im Worker und übergibt WaveSurfer eine `blob:`-URL. Ein Blob
kennt keine Range-Requests — die Datei muss vollständig vorliegen. Der
gesamte Streaming-Vorteil ist aufgehoben.

### 2. Der Download ist nicht abbrechbar

`workerFetch(url, onProgress)` nimmt keinen `AbortController`; im Modul gibt es
keinen. Weder der 60-s-Timeout noch das Unmounten stoppen den laufenden
Download — 47 MB laufen weiter, auch wenn der Player längst weg ist.

### 3. Timeout-Grenze wird auf Mobilfunk praktisch immer gerissen

Für den 47-MB-Preview im 60-s-Timeout (WebAudio-Zweig: 120 s):

| Bandbreite | Dauer | Ergebnis |
|---|---|---|
| 3 Mbit/s | 125 s | TIMEOUT |
| 6 Mbit/s | 63 s | TIMEOUT |
| 10 Mbit/s | 38 s | ok |

Nötig sind **6,3 Mbit/s** (60 s) bzw. **3,1 Mbit/s** (120 s), um den Timeout zu
schlagen. Alles darunter ist auf Mobilfunk der Normalfall.

### 4. Keine Längenprüfung — der abgeschnittene Puffer wird akzeptiert

`fetch.worker.ts`:

```js
const total = Number(resp.headers.get("content-length") || 0);
for (;;) { const { done, value } = await reader.read(); if (done) break; … }
const merged = new Uint8Array(received);   // ← received wird nie gegen total geprüft
raw = merged.buffer;
```

Bricht die Verbindung vorzeitig ab, meldet der Reader `done` und der
**unvollständige** Puffer geht weiter an `decodeToWav()`.

### 5. Der Decoder akzeptiert Truncation lautlos

Empirisch belegt — derselbe Decoder, der in Produktion läuft
(`decodeAudioData` im Browser, anonym gegen den Share getestet):

- Server liefert 3.000.000 Bytes von 46.949.384 (Range erfüllt)
- `decodeAudioData` → **`decode_fehler: null`**
- Ergebnis: **1021 s (17,0 min)** statt 15.718 s (262 min)

Gegenprobe mit dem Referenzdecoder (ffmpeg) auf derselben Scheibe:
`ffprobe duration=1021.0`, Exit-Code 0, vollständiger Decode ohne Warnung.

**Ein abgeschnittener Download wird also zu einem kürzeren Audio ohne jeden
Fehler.** WaveSurfer zeichnet eine Welle für 17 min bei einer 262-min-Aufnahme.

Das erklärt auch „nach einer Weile": die Korruption entsteht erst, wenn der
Download weit gelaufen und dann abgerissen ist.

## Fix

### a) Invariante im Worker (`fetch.worker.ts`)

Ein vorzeitig beendeter Stream wird zum **Fehler**, nie zur stillen Korruption.
Nur prüfen, wenn der Body nicht transformiert wurde (`content-encoding`
identity) — sonst würde ein gzip-Response falsch als unvollständig gelten, weil
`content-length` die komprimierte Größe nennt.

### b) MediaElement streamt statt zu laden (`WaveformPlayer.tsx`)

Im MediaElement-Modus den Worker überspringen und die URL direkt an `ws.load()`
geben. Die Wellenform kommt sofort aus den Server-Peaks, das Audio streamt per
Range-Request; der Browser puffert, seekt und wiederholt selbst. Damit entfällt
der 47-MB-Download für lange Aufnahmen vollständig.

Der Worker bleibt für den WebAudio-Pfad (kurze Dateien) erhalten — dort
vermeidet er den Decode auf dem Main-Thread. Für diesen Pfad greift (a).

## Auswirkung

- Lange Aufnahmen auf langsamer Leitung: kein Voll-Download, keine Blob-URL,
  damit kein Truncation-Pfad mehr — das gemeldete Symptom entfällt.
- Kurze Aufnahmen (WebAudio): unverändert im Ablauf, aber abgeschnittene
  Downloads werden jetzt als Fehler sichtbar statt still korrupt.
