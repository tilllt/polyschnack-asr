# Review: Offene Fragen der PolySchnack-Refactoring-Konzepte (108–110)

> Stand: 23.08.2026 · Zu reviewen mit Ruben (Signal) · Basis: die drei
> Konzept-Changes 108 (GUI/Timeline), 109 (Queue), 110 (Scheduling) +
> `refactoring-program.md`.

## Hintergrund in drei Sätzen

PolySchnack ist über Jahre gewachsen: Es gibt **drei getrennte Wahrheiten**
für dasselbe (Wort-Timestamps vs. Segment-Texte, RAM-Queue vs. DB-Status,
drei ETA-Schätzungen), und parallele Nebenläufigkeit an sechs+ Stellen.
Die drei Refactorings lösen das Schicht für Schicht mit demselben Prinzip:
**eine Quelle der Wahrheit statt Kopien.** Die folgenden 7 Fragen müssen
vor/mit der Umsetzung entschieden werden.

---

## Change 108 — GUI/Timeline („Timeline als Source of Truth")

### Frage 1: Was passiert mit bestehenden, manuell bearbeiteten Transkripten?

**Kontext:** Die neue Architektur speichert eine Wortliste mit absoluten
ms-Zeitstempeln als einzige Wahrheit. Heute leben die Bearbeitungen der User
(Text-Änderungen, Segmentgrenzen) in Yjs-Dokumenten (kollaborativer Editor).
Es gibt bereits etliche Aufnahmen mit manuell korrigiertem Text — dieser
Bestand ist wertvoll und darf nicht verloren gehen.

**Optionen:**
- (a) Migration: Alte Yjs-Dokumente werden beim Update einmalig in die neue
  Wortliste überführt (Wörter + Zeiten aus den Segmenten extrahiert).
- (b) Backfill: Die neue Struktur wird aus den vorhandenen Segment-Daten
  aufgebaut, ohne das Yjs-Dokument selbst zu konvertieren.

**Empfehlung:** (a) — einmalige Migration mit Abbruch-Sicherheit (Backup vor
dem Update), damit niemand seine Korrekturen verliert. Kostenpunkt: ein
Migrationstest mit Alt-Daten.

### Frage 2: Gehören Sprecher (Diarisation) zu Wörtern oder zu Segmenten?

**Kontext:** Bei der Sprecher-Erkennung bekommt jedes Segment einen Sprecher.
Wenn der User später eine Segmentgrenze verschiebt, „wandern" Wörter
zwischen zwei Segmenten — und damit zwischen zwei Sprechern. Entscheidet man
sich für **Segment-Sprecher**, ist die Logik einfach (ein Feld pro Segment),
aber beim Verschieben stimmt der Sprecher eines einzelnen Wortes evtl. nicht
mehr. Entscheidet man sich für **Wort-Sprecher**, bleibt jedes Wort beim
richtigen Sprecher, aber die Pflege ist aufwändiger.

**Empfehlung:** v1 = Sprecher am Segment (einfach, robust); Wörter erben den
Sprecher ihres Segments. Wort-Sprecher als spätere Verfeinerung.

### Frage 3: Wie zeigt man das Ergebnis einer Teil-Neutranskription?

**Kontext:** Change 108 bringt die Re-Transkriptions-Pipeline: Der User kann
einen Bereich (z. B. 5 Minuten) mit einem **anderen ASR-Modell** neu
transkribieren lassen, wenn das erste Modell dort schlecht war. Bevor der
neue Text übernommen wird, sollte man sehen, **was sich ändert**.

**Optionen:**
- (a) Diff-Vorschau direkt im Editor (alter Text vs. neuer Text, Änderungen
  markiert), der User übernimmt oder verwirft.
- (b) Nur eine Benachrichtigung („Bereich neu transkribiert"), der Text wird
  direkt übernommen.

**Empfehlung:** (a) — Diff im Editor. Passt zum Grundsatz „Anzeige = Export"
und verhindert Überraschungen bei 90-min-Aufnahmen.

---

## Change 109 — Queue („persistente Job-Tabelle statt RAM-FIFO")

### Frage 4: Was passiert mit Warteschlangen-Jobs nach einem Server-Neustart?

**Kontext:** Die Queue lebt heute im RAM des Servers. Startet der Server neu
(Deploy, Crash), bleiben alle Aufnahmen, die gerade „in der Warteschlange"
standen, **für immer in der Warteschlange** — sie werden nie transkribiert,
und der User sieht keinen Fehler (Zombie-Jobs). Der Fix ist klar (persistente
Job-Tabelle), aber es gibt eine ehrliche Design-Entscheidung:

**Optionen:**
- (a) Automatisch wieder einreihen: Nach dem Neustart laufen die Jobs einfach
  weiter — der User merkt nichts, wartet aber evtl. länger.
- (b) Ehrlich markieren: Jobs, die beim Neustart liefen, werden als
  „abgebrochen (Server-Neustart)" markiert; der User kann sie mit einem
  Klick neu starten.

**Empfehlung:** Hybrid: Noch **nicht** gestartete Jobs (queued) automatisch
wieder einreihen; gerade **laufende** Jobs ehrlich als abgebrochen markieren
(ihr Zwischenstand ist sonst nicht garantiert). So wird nichts still
verschluckt und nichts doppelt gearbeitet.

### (implizit in 109): Retry-Politik — siehe Frage 5

---

## Change 110 — Workflow-Scheduling („ein Job-Modell für alle Workflows")

### Frage 5: Sollen Hintergrund-Workflows (Align, Re-Diarize) automatisch wiederholt werden?

**Kontext:** Heute laufen Nachbearbeitungs-Jobs (präzises Wort-Alignment,
erneute Sprecher-Erkennung) als „Feuer-und-vergessen"-Threads: Schlägt einer
fehl, passiert nichts — kein Versuch, kein Fehlerbericht. Im neuen Modell
sind sie echte Jobs mit Fehlerbehandlung. Die Frage ist die Wiederhol-Politik:
transiente Fehler (Dienst kurz nicht erreichbar) sind oft beim 2. Versuch
weg; echte Fehler (defektes Audio) wiederholen sich sinnlos.

**Empfehlung:** Genau **1 automatischer Wiederholversuch** bei transienten
Fehlern (Zeitüberschreitung, Dienst nicht erreichbar), danach ehrlich
`failed` mit Grund — und manueller „Erneut versuchen"-Knopf für den Admin.
Wichtig: Der Versions-Schutz sorgt dafür, dass ein Wiederholversuch nie
doppelt schreibt (idempotent).

### Frage 6: Dürfen Nachbearbeitungs-Jobs die ASR-Kapazität belegen?

**Kontext:** Die Transkription (ASR) ist der Kern-Job. Ein 90-min-Job läuft
oft mehrere Minuten auf dem Backend. Wenn gleichzeitig Align/Diarize-Jobs
dieselben Backend-Plätze belegen, bremsen sie die eigentlichen
Transkriptionen aus — besonders bei mehreren Usern.

**Empfehlung:** Eigene Kapazitäts-Pools: ASR-Jobs und
Nachbearbeitungs-Jobs haben getrennte Semaphore. Nachbearbeitung nutzt
freie Kapazität, verdrängt aber nie eine laufende Transkription.

### Frage 7: Wie ehrlich soll der Fortschrittsbalken sein?

**Kontext:** Der Fortschrittsbalken zeigt heute einen Prozentwert je Phase.
Es gibt bereits eine lernende ETA (rtf_learner), die aus echten Messungen
weiß, wie lange eine Phase auf dieser Hardware dauert.

**Optionen:**
- (a) Feste Kacheln: ASR = 0–40 %, Align = 40–70 %, Rest = 70–100 %. Stabil
  und vorhersehbar, aber bei 90-min-Jobs springt der Balken lange nicht.
- (b) Dynamisch: Die Prozentbereiche kommen aus den gelernten Werten. Ehrlicher
  (die Kacheln entsprechen den echten Dauern), aber der Balken „springt"
  zwischen Aufnahmen.

**Empfehlung:** (b) dynamisch, mit Untergrenze für die Anzeige (z. B. nie
länger als X Sekunden auf demselben Prozentwert, solange der Job läuft —
verbunden mit dem Heartbeat, der zeigt, dass der Job lebt). Das ersetzt
„Fake-Fortschritt" durch echten, gemessenen Fortschritt.

---

## Ergebnis

| # | Frage | Empfehlung |
|---|-------|-----------|
| 1 | Alt-Transkripte migrieren? | Ja, einmalige Migration mit Backup |
| 2 | Sprecher an Wort oder Segment? | Segment (v1), Wörter erben |
| 3 | Diff-Vorschau bei Re-ASR? | Ja, im Editor |
| 4 | Neustart: queued vs. running | queued wieder einreihen, running ehrlich failed |
| 5 | Retry für Align/Diarize? | 1× automatisch, dann failed + manuell |
| 6 | Eigene Kapazität für Nachbearbeitung? | Ja, getrennte Pools |
| 7 | Feste oder dynamische Fortschritts-Kacheln? | Dynamisch (rtf_learner), mit Lebend-Heartbeat |
