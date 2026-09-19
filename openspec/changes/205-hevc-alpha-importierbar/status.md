# Status — Change 205

**Stand 19.09.2026:** Ursache belegt, Änderung umgesetzt und im Container nachgewiesen.
CI-Bau und Deploy stehen noch aus.

## Beweiskette (am Gerät, KineMaster 7.1)

- `hvcC` mit x265-Versions-SEI (2,3 kB `user_data_unregistered`) → **abgelehnt**
  (zwei Sonden, unterschiedliche Auflösung/Dauer — beide abgelehnt, also nicht die Größe).
- `hvcC` nur mit Alpha-SEI, Versions-SEI entfernt → **importiert** (Warnung IDR-Intervall).
- SEI in den Samples statt im `hvcC` → **importiert**.
- Referenz-Testclips (x265-CLI + Stream-Copy, SEI in den Samples) → importiert.

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
