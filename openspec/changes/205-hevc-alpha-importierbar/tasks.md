# Aufgaben — Change 205

- [x] Fehlerbild am Gerät abgegrenzt: „nicht unterstütztes Format" für Dienst-Ausgaben, während
      Testclips mit gleicher Signalisierung importierbar waren.
- [x] Fünf Sonden gebaut, die je ein Merkmal verändern (SEI-Lage, Auflösung/Dauer, Versions-SEI)
      und alle auf Zipline bereitgestellt.
- [x] Ergebnis ausgewertet: Versions-SEI im `hvcC` = Ablehnungsgrund; SEI in den Samples = harmlos;
      IDR-Abstand erzeugt Warnung.
- [x] `app.py`: `-x265-params info=0` und `-g <2 s>` für `hevc_alpha`.
- [x] `test_app.py`: beide Parameter als Regressionstest abgesichert.
- [x] Nachweis im Render-Container: `hvcC` nur noch mit Alpha-SEI, Versions-SEI weg, 8 Keyframes,
      Alpha an den Untertitelzeiten 255.
- [x] Testsuite: 20 passed, 1 skipped.
- [ ] CI (Harbor), Deploy des Render-Dienstes, echten Export am Handy testen.
