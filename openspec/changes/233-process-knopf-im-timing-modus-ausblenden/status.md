# Change 233 — Process-Knopf im Timing-Modus ausblenden

Nutzer-Vorgabe 21.09.2026, wörtlich:

> Im Timing Modus bitte den Process knopf ausblenden

## Ausgangslage

Change 208 hatte den Knopf im Timing-Reiter gesperrt, Change 210 ihn **sichtbar-aber-gesperrt** gelassen mit der Begründung, ein ausgeblendeter Block wirke beim Zurückwechseln „verschwunden" (Nutzer-Befund „danach fehlt der process button immer noch"). Diese Begründung ist entfallen: seit Change 232 trägt der Timing-Reiter seinen eigenen Zustandshinweis.

## Umsetzung

- Der Block (Process-Knopf **und** die Beschriftung daneben) wird nur noch gerendert, wenn `editorTab !== "timing"`.
- Damit entfallen die timing-spezifischen Zweige am Knopf: `disabled={startDisabled || editorTab === "timing"}`, `title` und `data-timing-disabled`. Der Knopf ist außerhalb des Timing-Reiters unverändert.
- Der alte Test „Start-Knopf bleibt sichtbar, ist im Timing-Tab aber nicht bedienbar (Change 210)" ist auf die neue Erwartung umgestellt: im Timing-Reiter ist `process-btn` **nicht im DOM** (`queryByTestId → null`), in der Transkription sichtbar und bedienbar.

## Prüfstand

- Frontend: 51 Dateien / 602 Tests grün, tsc ohne Fehler (Lauf mit dieser Änderung läuft erneut).
- Offen: Ausrollen zusammen mit 231/232.
