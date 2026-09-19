# Status — Change 205

**Stand 19.09.2026: umgesetzt, gebaut, deployt und im Betrieb nachgewiesen.**

## Beweiskette (am Gerät, KineMaster 7.1)

- `hvcC` mit x265-Versions-SEI (2,3 kB `user_data_unregistered`) → **abgelehnt**
  (zwei Sonden, unterschiedliche Auflösung/Dauer — beide abgelehnt, also nicht die Größe).
- `hvcC` nur mit Alpha-SEI, Versions-SEI entfernt → **importiert** (Warnung IDR-Intervall).
- SEI in den Samples statt im `hvcC` → **importiert**.
- Referenz-Testclips (x265-CLI + Stream-Copy, SEI in den Samples) → importiert.

## Abnahme im Betrieb

- CI: Pipeline #5397 für Commit `8679982` — `build-render` 51 s und `test-render` 132 s grün.
- Deploy: `ps-render` mit vier Overlays plus `--profile render` neu erstellt;
  Revision im Image `86799825`, Container gesund, `/health` = `ok` mit `libx265`-Fähigkeit.
- **Ende-zu-Ende mit dem deployten Code:** `build_ffmpeg_args` für `hevc_alpha` enthält
  `-g 50 -x265-params info=0`; ein Probe-Export über diesen Pfad läuft mit rc 0 und liefert eine
  Datei mit `hvcC` = VPS 1×, SPS 2×, PPS 2×, **SEI 1×** und **ohne** die x265-Versions-SEI.
- Am Gerät geprüft: korrigierter Export (gleiche Untertitel, gleiche Größe) importiert.

## Offen (Nutzer)

- Echter Export aus der Webapp und Import am Handy.


## Nachweis der Behebung (Container, noch ohne Deploy)

- `hvcC`: VPS 1×, SPS 2×, PPS 2×, **SEI 1× (Alpha)** — wie Apples `dsh_pet.mov`.
- `x265 (build` im File: nicht mehr vorhanden.
- Keyframes: 8 statt 2 bei 385 Bildern (IDR-Abstand ≈ 1,9 s).
- Alpha an Untertitelzeiten: Maximum 255, vor dem ersten Untertitel (1,44 s) 0.
- Tests: 20 passed, 1 skipped.

## Offen

- CI-Bau und Deploy; anschließend echter Export aus der Webapp und Import am Handy.
- Falls KineMaster weitere Hürden zeigt: die Sonden liegen als Vergleichsdateien bereit
  (`/opt/data/hevc-alpha-tests/` mit `ERGEBNISSE.md`).
