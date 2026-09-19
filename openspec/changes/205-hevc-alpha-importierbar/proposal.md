# Change 205 — `hevc_alpha` in KineMaster importierbar machen

## Warum

Der Dienst erzeugte HEVC-mit-Alpha-Dateien, die **KineMaster 7.1 mit „Dieser Clip enthält ein
nicht unterstütztes Format" ablehnte** — obwohl die Signalisierung stimmt (`scalability_mask=0x3000`,
`AuxId=1`, SEI 165, `hvc1`) und obwohl Testclips mit derselben Signalisierung importierbar waren.

Ursache am Gerät eingekreist (fünf Sonden, 19.09.2026, jeweils nur ein Merkmal verändert):

- **Sonde 3** (960×540, 5 s, SEI **nur im `hvcC`**, inkl. x265-Versions-SEI) → **abgelehnt**
- **Sonde 1** (1080×1920, 15,4 s, SEI nur im `hvcC`, inkl. Versions-SEI) → **abgelehnt**
- **Sonde 2** (1080×1920, 15,4 s, SEI im `hvcC`, **ohne** Versions-SEI) → **importiert**, aber Warnung
  „IDR-Intervall ist zu groß"
- **Sonde 4** (960×540, 5 s, SEI **in den Samples**, keine SEI-Array im `hvcC`) → **importiert**
- Referenz: Testclips mit x265-CLI-Encode + Stream-Copy (SEI in den Samples) → importiert

Damit war klar: nicht die Signalisierung ist das Problem, sondern die **~2,3 kB große
`user_data_unregistered`-SEI mit dem x265-Versionsstring im `hvcC`** (Sample Description). Sie
entsteht, wenn ffmpeg den Strom selbst erzeugt (die SEI-NALs wandern in die Extradata), und
KineMaster lehnt solche Dateien komplett ab. Dieselbe SEI **in den Samples** ist harmlos. Ohne sie
bleibt im `hvcC` nur die 4-Byte-Alpha-SEI — das entspricht Apples Referenzaufbau und wird
importiert.

Zweiter Fund derselben Messreihe: x265 nimmt `keyint=250` (10 s bei 25 fps); KineMaster warnt
deshalb „IDR-Intervall ist zu groß".

## Was sich ändert

1. `hevc_alpha` kodiert mit **`-x265-params info=0`** — die Versions-SEI entsteht gar nicht mehr.
2. `hevc_alpha` kodiert mit **`-g <2 s>`** (`keyint = 2 × fps`) — kurzer, gleichmäßiger IDR-Abstand,
   keine Warnung mehr, besseres Scrubben.
3. Regressionstests sichern beides ab (`test_app.py`), damit die Parameter nicht „aufgeräumt" werden.

## Belege nach der Änderung

- `hvcC` der neuen Datei: VPS 1× Layer 0, SPS 2× (L0/L1), PPS 2× (L0/L1), **SEI-prefix 1× (nur die
  4-Byte-Alpha-SEI)** — genau Apples Aufbau (`dsh_pet.mov`).
- Zeichenkette `x265 (build` im ganzen File: **nicht mehr vorhanden**.
- 385 Bilder → **8 Keyframes** (vorher 2), IDR-Abstand ≈ 1,9 s.
- Alpha unverändert korrekt: an den Untertitelzeiten (3 s / 6 s / 10 s) Alpha-Maximum 255, davor 0
  (der erste Untertitel beginnt bei 1,44 s).
- Tests: `20 passed, 1 skipped` (der übersprungene braucht das Alpha-fähige ffmpeg und läuft im
  Image).

## Abgrenzung

- Betrifft nur das Format `hevc_alpha`. `alpha_webm`, `alpha_mov`, `alpha_png`, `burn_mp4`/`chroma_mp4`
  bleiben unverändert.
- Kein Eingriff in Signalisierung, Container-Metadaten (`muxa`/`almo`) oder die Alpha-Erzeugung
  selbst. Die x265-`0x3000`-Signalisierung bleibt wie sie ist — KineMaster akzeptiert sie
  (Sonde 2/4 mit `0x3000` importieren).
