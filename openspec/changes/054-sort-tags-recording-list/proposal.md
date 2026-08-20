# Change 054 — Sortierung + Tags in der Recording-Liste

## Problem

Die Recording-Liste ist fest nach `created_at DESC` sortiert (`crud.list_recordings`,
Z. 115). Bei den inzwischen 60+ Aufnahmen auf der Box (und den historischen
Korpora aus Change 025: 33 Walzen + 14 Schellack) gibt es keine Möglichkeit,
die Ansicht nach anderen Kriterien zu ordnen. Außerdem fehlt jede
Gruppierungs-/Markierungsmöglichkeit: Man kann eine Transkription nicht als
„Walze", „Schellack", „zu korrigieren", „fertig" o. ä. kennzeichnen und danach
filtern — die Suche (q) durchsucht nur Text/Name.

## Ziel (wörtliche User-Vorgabe, 2026-08-20)

1. **Sort-Badges** über der Liste:
   **Date** · **Last edit date** · **Name (alphabetisch)** · **Filename (alphabetisch)** · **Length**
   - 1. Klick auf ein Badge: **absteigend** sortieren (desc).
   - 2. Klick auf dasselbe Badge: **aufsteigend** sortieren (asc).
     (Die Vorgabe nennt „zweimal klick … abwärts"; als einzige sinnvolle
     Lesart wird ein Toggle desc → asc umgesetzt.)
   - 3. Klick: Sortierung zurücksetzen → Default `Date desc`, kein Badge aktiv.
2. **Tags:** Transkriptionen können **Tags zugewiesen** werden (mehrere pro
   Aufnahme, frei wählbar, z. B. „Walzen", „Schellack", „review", „fertig").
3. **Tag-Filter:** Der View kann **nach Tags gefiltert** werden. Es werden nur
   Tags mit ≥ 1 Aufnahme angeboten (analog zur Benchmark-Matrix-Regel
   „nur Kategorien mit mehr als 0 Samples"). Filter und Suche sind kombinierbar.

## Architektur

- **Sortierung + Filter im Backend** (`GET /api/recordings`): Query-Parameter
  `sort=date|edited|name|filename|length`, `dir=asc|desc`, `tag=<tag>`
  (exakter Treffer, mehrfach kombinierbar: `tag=A&tag=B` = UND? → **ODER**,
  da Tags freie Kennzeichnungen sind; dokumentiert in den Tasks). Default
  bleibt unverändert `date desc`. Sortierung im Backend hält die API zur
  Suche (`q`) konsistent — eine Quelle der Wahrheit, testbar in crud.
- **Tags-Datenmodell:** `tags: List[str]` als **JSON-Spalte** am `Recording`
  (SQLAlchemy `JSON`, wie `segments`/`waveform_peaks`). Keine Join-Tabelle —
  Tags sind flache, freie Labels; Abfrage per `LIKE` auf die JSON-Serialisierung
  (Muster: `Recording.tags` als Text durchsucht) bzw. ODER-Vergleich im
  Python-Filter. Migration: **Auto-ALTER beim Start** (bestehendes Muster
  „fehlende Spalten per `PRAGMA table_info` ergänzen").
- **„Last edit date":** Basis ist `rec.updated_at`. **Lücke:** Segment-Änderungen
  (`PUT /api/recordings/{rid}/segments`, `PATCH …/segments/{sid}` und der
  Yjs-Finalize über PUT) aktualisieren `updated_at` aktuell **nicht** —
  sie werden es künftig tun, damit „Last edit" die tatsächliche letzte
  Bearbeitung abbildet.
- **Tag-Schreibzugriff:** `PATCH /api/recordings/{uid}/tags` mit Body
  `{"tags": [...]}` — Auth wie Segment-Edit (**write**-Zugriff, Owner/Share).
- **Frontend:** Badge-Leiste über der Liste (aktives Badge hervorgehoben mit
  ↑/↓), Tag-Filter-Chips (Aggregation aus der geladenen Liste, mit Count),
  Tag-Editor in der RecordingCard (Chips + Eingabe + Enter). i18n de/en über
  die bestehende `useT`-Mechanik. Die Liste wird weiterhin vollständig
  geladen (kein Server-Paging) → Aggregation der Tag-Liste im Client OK.

## Requirements

- **REQ-UI-054-01:** Fünf Sort-Badges (Date, Last edit, Name, Filename, Length);
  Klick-Zyklus desc → asc → Default; aktives Badge klar markiert.
- **REQ-UI-054-02:** Sortierung wirkt auf die komplette sichtbare Liste
  (auch bei aktiver Suche), Default ist `Date desc` (heutiges Verhalten).
- **REQ-UI-054-03:** Tags pro Aufnahme: hinzufügen, entfernen, mehrere gleichzeitig;
  Persistenz im Backend (write-Zugriff), sichtbar in der Card.
- **REQ-UI-054-04:** Tag-Filter-Leiste zeigt nur Tags mit ≥ 1 Aufnahme (mit Count);
  aktive Filter-Chips hervorgehoben; kombinierbar mit Suche `q`.
- **REQ-UI-054-05:** „Last edit date" = `updated_at`, aktualisiert bei jeder
  Segment-Änderung (PUT/PATCH segments, inkl. Yjs-Finalize) und Titel-Edit.

## Nicht-Ziele

- Keine Server-Pagination (Liste bleibt vollständig geladen).
- Keine Tag-Verwaltung (Farben, feste Kategorien) — freie Text-Labels.
- Kein Einfluss auf den Benchmark-Ownership-Workflow (Change 026).
