# Change 238 — Wartungsauftrag: ausstehende Alignments nachziehen

**Status:** Fix fertig, Prüfungen laufen
**Datum:** 30.09.2026
**Bezug:** Change 237 (Ursache behoben), Nutzer-Antwort im Thread:

> 2 ja

(Bezug war die Frage: „Sollen die 103 Aufnahmen ohne feines Alignment
nachgezogen werden?")

## Ausgangslage

Change 237 hat die Ursache behoben: Das Hintergrund-Alignment wurde aus dem
laufenden Transkriptions-Job heraus eingereiht und vom Ein-Job-Wächter
abgelehnt — die präzisen Wortzeiten entstanden seit Change 173 (Ende August)
nie mehr automatisch. Für **neue** Aufnahmen ist das damit erledigt.

Die Aufnahmen aus dem Ausfallzeitraum bleiben aber mit den groben Wortzeiten
des Transkriptionslaufs stehen. Gemessen auf der KI-Box (30.09.2026):

- **103 von 116** Aufnahmen haben keinen `align`-Job.
- Die 13 mit Job sind die von Hand ausgelösten (Aufnahme 328 sechsmal,
  341 und 329 je zweimal) — jüngster align-Job 19.09.2026.
- Die Spalte `alignment` steht bei 111 Aufnahmen auf `done`, bei 5 auf
  `skipped`; `done` sagt hier nur „der Lauf hat Wortzeiten geliefert", nicht
  „akustisch geprüft".

## Lösung

Ein **Wartungsauftrag**, der nur auf ausdrückliche Anforderung läuft — kein
Dauerbetrieb, kein Automatismus:

- Ohne die Datei `.align-backfill` im Datenverzeichnis tut der Auftrag
  **nichts**. Liegt sie dort, reiht der nächste Takt Aufträge ein.
- Er läuft als **Task der Scheduler-Registry** (`align-backfill`, alle 30 s) —
  dasselbe Muster wie `peaks-backfill`, **kein eigener Thread** (der CI-Wächter
  verbietet nackte Threads in `app/`; Arbeit gehört über die Queue oder die
  Registry). Jeder Takt reiht bis zu `WAVE=4` Aufträge ein und ist sofort
  wieder fertig — kein Schlafen im Task, kein Überlappen.
- Er zieht fertige Aufnahmen **ohne `align`-Job** nach, neueste zuerst. Maßstab
  ist die **Job-Tabelle**, nicht das Feld `alignment`: das steht auch dann auf
  `done`, wenn nur die groben Wortzeiten des Transkriptionslaufs existieren.
- Die Aufträge laufen mit **Priorität 1** — wie anonyme Jobs, also hinter der
  Arbeit eines angemeldeten Nutzers. Dafür hat `_schedule_realign` einen
  `priority`-Parameter bekommen (Standard 0, unverändertes Verhalten).
- **Start und Abbruch ohne Neustart:** Datei anlegen startet die Wartung
  (innerhalb eines Takts), Datei löschen beendet sie. Nach der letzten offenen
  Aufnahme meldet der Task einmal „nichts mehr offen".
- Aufnahmen ohne Audio (Datei fehlt) werden gemerkt und **nicht** erneut
  versucht — sonst käme der Task an derselben Aufnahme nie vorbei.

Was dabei **nicht** passiert: Text, Segmente und Sprecher bleiben unangetastet.
Es entsteht der reguläre `align`-Queue-Job (Change 046/155); der Worker
bereitet das Audio selbst aus der gespeicherten Datei und den Run-Einstellungen
vor (`_prepare_align_audio`) und der Versions-Guard verwirft das Ergebnis, wenn
die Segmente sich während des Laufs geändert haben.

## Nebenfund und Mitbehebung

`_schedule_realign` setzte `alignment = "pending"` **vor** dem Einreihen. Schlug
das Einreihen fehl (`QueueError`, z. B. weil die Aufnahme schon belegt war),
blieb „pending" stehen — die Oberfläche hätte dauerhaft „Ausrichtung läuft"
gezeigt, obwohl kein Job existiert. Für einen einzelnen Klick fiel das kaum
auf; ein Wartungsauftrag, der reihenweise einreiht, macht daraus viele
Karteileichen. Jetzt wird der vorherige Zustand bei einem Fehlschlag
zurückgenommen.

## Prüfungen

`webapp/tests/test_align_backfill_238.py` (7 Prüfungen, alle grün):

- Kandidaten: nur fertige Aufnahmen ohne `align`-Job, neueste zuerst —
  Maßstab ist die Job-Tabelle, nicht das Feld `alignment`.
- Auftragsdatei: ohne Datei tut der Takt nichts (nichts wird eingereiht).
- Takte: 5 Kandidaten, `limit=2` → 2/2/1/0; Reihenfolge neueste zuerst; alle
  Aufträge mit Priorität 1; Bilanz `enqueued=5`.
- Aufnahme ohne Audio: einmal versucht, gemerkt, nicht wiederholt — die übrigen
  laufen weiter (Ausschluss steckt in der Abfrage, nicht hinter dem `LIMIT`).
- Datei löschen: nächster Takt beendet den Auftrag und setzt die Bilanz zurück.
- Registrierung: `align-backfill` steht in der Scheduler-Registry.

## Ablauf auf der KI-Box

1. Rollout (Change 237 + 238) nach grünem CI-Job `build-webapp`.
2. `docker exec polyschnack-ps-webapp-1 touch /data/.align-backfill`.
3. Abwarten — innerhalb von 30 s beginnt der erste Takt; Fortschritt im
   Container-Protokoll (`Wartungsauftrag align-backfill: …`) und über die
   align-Jobs in der Datenbank. **Kein Neustart nötig.**
4. Erste Takte beobachten (läuft ein align-Job wirklich durch? ändern sich die
   Wortzeiten einer Beispielaufnahme?), dann laufen lassen.
5. Abbruch jederzeit: `rm /data/.align-backfill` — greift beim nächsten Takt.
6. Danach die Bilanz dokumentieren (wie viele Aufnahmen wirklich nachgezogen
   wurden, wie viele ohne Audio blieben).
