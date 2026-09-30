# Change 236 — Serverweite Auskünfte werden EINMAL je Seite geholt

**Status:** Fix fertig, Invariante drin, CI-Nachweis und Rollout laufen
**Datum:** 30.09.2026
**Bezug:** Nutzer-Meldung „polyschnack ist grade abgestürzt, debugge"

Nutzer-Vorgabe, wörtlich:

> ja mache spec und optimiere

## Symptom

Der Nutzer (14:30 Ortszeit) meldete einen Absturz. Die Seite wirkte
eingefroren, er lud sie in zwei Minuten **dreimal** neu
(`GET /` 12:28:48, 12:29:48, 12:30:41 UTC).

**Der Dienst selbst war nie betroffen** — geprüft am lebenden System:

- Container `polyschnack-ps-webapp-1`: `RestartCount 0`, läuft seit
  29.09. 15:06 durch, Log zeigt genau einen „Application startup complete".
- 24 h Log: **2474× 200**, 7× 201 (neue Aufnahmen), 2× 404 (eigene Sonden),
  3× 502 (29.09. 15:07, OpenAI-Schnittstelle mit nicht laufendem Backend —
  separater Fall). Kein 5xx aus dem normalen Betrieb.
- Kein OOM (`dmesg` leer), Speicher 20/62 GB belegt, Platte 49 %.
- Die letzte Aufnahme des Nutzers (rec 362, 12:29:12 angelegt,
  12:31:05 transkribiert) ist **done** — Text, Wortzeiten und Sprecher da,
  `alignment: done`, kein Fehler. Die Reihenfolge der Jobs ist vollständig.

## Ursache (gemessen, nicht geschlossen)

Nicht der Server war das Problem, sondern die **Zahl der Anfragen, die ein
einziger Seitenaufruf auslöst**. Die Aufnahmenliste rendert jede Aufnahme als
eigene Karte; **jede Karte holte beim Aufbau für sich sieben serverweite
Auskünfte**, die für alle Karten identisch sind: Modell-Matrix,
Backend-Fähigkeiten, Modell-Status, Vorlagen, Format-Vorgaben, Zustellziele,
LLM-Adressen — und je Karte zusätzlich die Export-Vorlagen.

Messung im Server-Protokoll (Kartei: 116 Aufnahmen in der Datenbank), Lawine
vom 30.09. 12:29:47 UTC:

```
Dauer 24 s, 872 Anfragen (36/s, Spitze 111/s)
  116× /api/backends            116× /api/formatting/presets
  116× /api/models/status       114× /api/templates
  114× /api/targets             114× /api/llm-endpoints
  113× /api/export-templates     54× /api/models/matrix
```

Identisch am 29.09. 16:07 (112 Karten, 846 Anfragen in 22 s) — also
reproduzierbar, nicht einmalig.

Wirkung auf die Box im selben Moment:

- Last (1 min) **16,7** — normal 1–4.
- Netzwerk-Unterbrechungen (`system.cpu`/irq, Netdata-Verlauf): **17,5 %**
  um 12:30 UTC gegenüber ~5 % im Tagesmittel.
- Der Tab war ~24 s nur mit Abfragen beschäftigt → „Seite hängt".

Der Anteil ist genau die Kartenzahl: 116 Karten × 7 = 812, dazu die
Export-Vorlagen. Bei 300 Aufnahmen wären es über 2400 Abfragen.

## Umsetzung

- **Neu `webapp/frontend/src/sharedConfig.ts`:** `once(schlüssel, laden)`
  teilt eine laufende oder frisch abgeschlossene Abfrage zwischen allen
  Aufrufern (30 s Ablaufzeit). Fehler werden **nicht** gemerkt — schlägt eine
  Abfrage fehl, versucht es der nächste Aufruf erneut (die Karten haben
  eigene Rückfallwerte, z. B. hartkodierte Exportformate).
- **`RecordingCard.tsx` und `UploadZone.tsx`** holen die sieben Auskünfte und
  die Export-Vorlagen jetzt über `sharedConfig` statt direkt. Die Karten
  behalten Zustandsfelder und Vorgehen; getauscht ist nur die Quelle. Kein
  Umbau auf einen Daten-Cache, damit Verhalten und Rückfallwerte unverändert
  bleiben.
- **Nicht** über `once()` laufen die bewussten Nachlade-Knöpfe
  (`PostProcessPanel`: Vorlagen/Ziele/Endpunkte auf Klick) — dort ist eine
  frische Antwort gewollt.
- **Test-Setup:** `vite.config.ts` lädt `src/testSetup.ts`, das vor jeder
  Prüfung `forgetSharedConfig()` ruft. Ohne das erbte eine Prüfung die
  Auskunft der vorigen (der Geteiltenspeicher soll ja leben).

Ergebnis: **aus ~812 Anfragen werden 8** (sieben Auskünfte + Export-Vorlagen),
unabhängig von der Zahl der Aufnahmen.

## Prüfstand

- **`src/sharedConfig.test.ts`** (7 Prüfungen): gleichzeitige Aufrufe ergeben
  EINE Abfrage; innerhalb der Ablaufzeit kommt die geholte Auskunft; nach dem
  Ablauf wird neu geholt; Fehler werden nicht gemerkt; `forgetSharedConfig`
  leert gezielt; Ablaufzeit plausibel; verschiedene Schlüssel bleiben getrennt.
- **`src/components/RecordingList.sharedConfig.test.tsx`** (3 Prüfungen):
  zählt die Anfragen an der **Netzwerk-Grenze** (`fetch`-Stub), nicht an einem
  API-Mock — damit ist die Prüfung unabhängig davon, über welchen Pfad eine
  Komponente die Auskunft holt. Acht Karten → jede Auskunft genau einmal;
  zwanzig Karten → **8 Anfragen** (vorher 160); nach `forgetSharedConfig` wird
  wieder geholt.
- **Rote Gegenprobe:** den Ablauf-Treffer in `once()` stillgelegt
  (`if (false && …)`) → alle drei Prüfungen **rot** (8 Karten: mehrfach
  geholt); zurückgenommen → grün.
- **Voller Frontend-Lauf:** `npx tsc -p tsconfig.json --noEmit` sauber,
  `vitest run` → **612 Prüfungen in 53 Dateien grün**.

## Lernhinweis (warum es nicht vorher auffiel)

Die Karten-Tests mocken `../api` und prüfen Verhalten, nicht Mengen. Eine
Karte für sich ist harmlos — erst die Vervielfachung durch die Liste ergibt
den Sturm. Die neue Prüfung zählt deshalb die Anfragen **je Seite**, nicht je
Komponente: sie wird rot, sobald eine Komponente wieder selbst holt.

## Offene Punkte (nicht Teil dieses Changes)

- **Weiches 404:** Ein fremder Scanner fragte um 01:55 `/.env`,
  `/.aws/credentials` und 39 weitere Pfade ab und bekam **41× „200 OK"**,
  weil der SPA-Rückfall für jeden unbekannten Pfad die Startseite liefert
  (Text/html, 1261 Bytes — **kein** Datenabfluss). Sauberer wäre 404 für
  Pfade außerhalb der Routen.
- `index.html` hat als Sprache fest `lang="pt-br"` (Deutsch ist Hauptsprache).
- Wettlauf in der Hintergrund-Ausrichtung: `bg-align: enqueue fehlgeschlagen
  rec_id=362: recording 362 already has an active job` — hier unschädlich
  (`alignment: done` durch den ersten Durchlauf), aber der zweite Anlauf
  entfällt stillschweigend.

## Ausgerollt

_(wird nach Rollout eingetragen: Pipeline, Revision vor/nach, Gegenprobe am
lebenden System — Anzahl der Anfragen eines echten Seitenaufrufs)_
