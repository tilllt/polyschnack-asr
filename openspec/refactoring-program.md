# Refactoring-Programm: Ausführungs- & Daten-Schicht (Changes 108–110)

> Stand: 23.08.2026. Überblick über die drei Refactoring-Changes — bewusst
> KEIN einzelner Change, sondern ein Programm mit fester Reihenfolge.

## Warum drei Changes statt einem

OpenSpec-Regel: **ein Change = eine fokussierte Verhaltensänderung**, klein
genug für ein Review und einzeln deploybar. Die drei Refactorings sind zwar
verzahnt, aber klar trennbar:

| Change | Ebene | einzeln deploybar? |
|---|---|---|
| [108-gui-timeline-refactor](108-gui-timeline-refactor/) | Datenmodell + Frontend (Timeline als Source of Truth) | ja (nach 110, reprocess braucht den Unterbau) |
| [109-queue-refactor](109-queue-refactor/) | ASR-Job-Schicht (persistente Job-Tabelle) | **sofort** — Zombie-Fix ist akut und unabhängig |
| [110-workflow-scheduling-refactor](110-workflow-scheduling-refactor/) | Workflow-Orchestrierung (Phasen-Registry, ein Job-Modell) | ja (baut auf 109 auf) |

Ein Mega-Change würde den Zombie-Job-Sofortfix (109) an das große
Frontend-Refactoring (108) ketten — ein akuter Bug müsste dann auf die
GUI-Umbauten warten. Getrennt bleiben die Changes einzeln reviewbar,
einzeln testbar und einzeln deploybar (CI-Pipeline je Change).

## Gemeinsamer Nenner (ein Design-Prinzip)

Alle drei lösen dieselbe Grundkrankheit in unterschiedlichen Schichten:

> **Eine Wahrheit statt gewachsener Kopien.**
> - 109: eine Job-Tabelle statt RAM-Dict + DB-Status + Router-Berechnung.
> - 110: eine Phasen-Registry + ein Heartbeat + ein Job-Modell statt
>   Monolith, drei Heartbeat-Kopien und fire-and-forget-Threads.
> - 108: eine Wort-Timeline statt Segment-Text + Wort-Arrays, die driften.

## Reihenfolge & Abhängigkeiten

```
109 (Job-Tabelle, Rehydration, Retry)
   ↓  Job-Runner als Basis
110 (alle Workflows als Jobs, Phasen-Registry, run_workflow)
   ↓  Wiedereinstiegspunkt
108 (reprocess-Pipeline + Frontend-Timeline-Refactor)
```

- **109 zuerst:** akut (Zombie-Jobs), unabhängig, kleinste Review-Fläche.
- **110 danach:** nutzt den Job-Runner; ohne 109 wäre es nur ein
  Thread-Umbau ohne Persistenz-Gewinn.
- **108 zuletzt:** reprocess (M3) braucht `run_workflow` (110 K5);
  die Sofort-Fixes F2 (Auto-Region) und B3 (llm_enhance words) sind
  davon unabhängig und können jederzeit vorab laufen.

## Was am Ende in die Specs wandert (openspec/specs/)

- `backend-queue` (bestehend): wird auf die persistente Job-Tabelle
  aktualisiert (109 J1–J5).
- `postprocessing` (bestehend): Phasen-Registry + Workflow-Typen ergänzen
  (110 K1/K2).
- neu `workflow-scheduling`: WORKFLOWS-Definitionen, Heartbeat-Muster,
  run_workflow-API (110).

## Meilensteine

- **M0 (Sofort-Fix, ohne Programm):** 109-Zombie-Schutz minimal
  (Restart → queued ehrlich failed) + 108-F2/B3.
- **M1:** 109 komplett (Job-Tabelle, Rehydration, Retry, ETA-zentral,
  Admin-API/UI).
- **M2:** 110 (Phasen-Enum, WORKFLOWS, align/rediarize als Jobs,
  ein Heartbeat, SCHEDULED_TASKS).
- **M3:** 108 (Datenmodell, Timeline-Store, reprocess, Playback-Sync).
