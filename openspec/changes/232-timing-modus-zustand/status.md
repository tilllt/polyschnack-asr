# Change 232 — Timing-Modus ohne Inhalt: „Not available in timing mode"

Nutzer-Befund 21.09.2026, wörtlich:

> wenn man bei einer sehr langen datei dann schnell zum timing fenster wechselt zeigt er einem noch nicht den detail view, stattdessen die inhaltslose fehlermeldung: Not available in timing mode — switch back to transcription first.

## Befund

Die Meldung ist der Sprachschlüssel `start_disabled_timing` — die Beschriftung neben dem gesperrten Process-Knopf (`RecordingCard.tsx`, Zeile 1735 ff.). Inhaltlich hatte der Timing-Reiter für eine noch nicht transkribierte Aufnahme **gar keinen Zustand**: bei `segments.length === 0` rendert der Bearbeitungsbereich nichts, und das Einzige, was zu lesen war, war dieser Satz.

## Umsetzung

Der Timing-Reiter rendert bei `segments.length === 0` einen Zustandsblock mit echtem Fortschritt:

- läuft ein Job (oder ist eine Prozentzahl angefangen): „Wortzeiten entstehen noch — diese Aufnahme wird gerade transkribiert ({p} %)" plus Fortschrittsbalken mit der Server-Prozentzahl
- sonst: „In diesem Reiter werden Wortzeiten bearbeitet. Diese Aufnahme hat noch keine — starte im Transkript-Reiter zuerst die Transkription."

Neue Sprachschlüssel `timing_waiting` und `timing_idle` in de/en/pt, ohne Fachbegriff. Prüfmerkmal in der Oberfläche: `data-testid="timing-waiting-<uid>"`.

Die Entscheidung „läuft" hängt an den Fortschrittswerten (`r.job.pct`, `r.progress_pct`), nicht am Status-Text — der Status ist in diesem Zweig bereits auf `done` eingeengt.

## Offen

- Ausrollen zusammen mit 231/233; Abnahme am Gerät.
