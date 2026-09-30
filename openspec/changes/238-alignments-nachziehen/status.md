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

- Ohne die Datei `.align-backfill` im Datenverzeichnis passiert beim Start
  **nichts**. Liegt sie dort, startet die Anwendung (Lifespan) einen
  Hintergrund-Thread.
- Er zieht fertige Aufnahmen **ohne `align`-Job** nach, neueste zuerst,
  gedrosselt in Wellen (`WAVE=4`, dazwischen `PAUSE_S=20`).
- Die Aufträge laufen mit **Priorität 1** — wie anonyme Jobs, also hinter der
  Arbeit eines angemeldeten Nutzers. Dafür hat `_schedule_realign` einen
  `priority`-Parameter bekommen (Standard 0, unverändertes Verhalten).
- **Abbruch jederzeit** durch Löschen der Datei; er greift nach der laufenden
  Welle. Nach der letzten offenen Aufnahme endet der Lauf von selbst.
- Aufnahmen ohne Audio (Datei fehlt) werden gemerkt und **nicht** erneut
  versucht — sonst liefe die Schleife endlos gegen dieselben Kandidaten.

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

`webapp/tests/test_align_backfill_238.py` (8 Prüfungen, alle grün):

- Kandidaten: nur fertige Aufnahmen ohne `align`-Job, neueste zuerst —
  Maßstab ist die Job-Tabelle, nicht das Feld `alignment`.
- Wellen und Ende: 5 Kandidaten, `wave=2`, in mehreren Runden; Bilanz
  `enqueued=5`, Ende `nichts-mehr-offen`; alle Aufträge mit Priorität 1.
- Abbruch: Datei verschwindet während der Welle → Ende `abgebrochen`, danach
  wird nichts mehr eingereiht.
- Aufnahme ohne Audio: einmal versucht, gemerkt, nicht wiederholt.
- Obergrenze (`max_total`) und `stop_event`.
- Start über die Anwendung: ohne Datei startet nichts, mit Datei genau ein Lauf.

## Ablauf auf der KI-Box

1. Rollout (Change 237 + 238) nach grünem CI-Job `build-webapp`.
2. `touch /data/.align-backfill` im Container.
3. Container neu starten → der Auftrag läuft im Hintergrund; Fortschritt im
   Protokoll (`Wartungsauftrag align-backfill beendet: {…}`) und über die
   align-Jobs in der Datenbank.
4. Beobachtung über die ersten Wellen; bei Bedarf Datei löschen = Abbruch.
5. Danach die Bilanz dokumentieren (wie viele Aufnahmen wirklich nachgezogen
   wurden, wie viele ohne Audio blieben).
