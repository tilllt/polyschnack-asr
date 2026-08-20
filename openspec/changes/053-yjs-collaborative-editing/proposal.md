# Change 053 — Yjs-Kollaboration im Transkriptions-Editor

## Problem

Der Edit-Modus der Transkriptionen ist **solo**: Nur ein Nutzer kann eine
Transkription zu einem Zeitpunkt bearbeiten, Änderungen anderer Reviewer
gehen verloren oder erzeugen Merge-Konflikte. Für den Ground-Truth-Workflow
(Change 025/026) ist das ein Engpass: Die Projektleitung korrigiert die
Vortranskriptionen der 33 Walzen (+ 14 Schellack) manuell — mehrere
Korrektur-Personen (oder Hermes parallel zur Projektleitung) können nicht
gleichzeitig an derselben Transkription arbeiten. Zusätzlich fehlt die
**Export-Brücke** zwischen Editor und Ownership-Mechanismus: Der finale
Text muss nach `accept` als Klartext je Segment in
`transcripts/user/<sample>.txt` landen (Change 026), heute müsste das
per Hand kopiert werden.

## Ziel

1. **Kollaborativer Edit-Modus** im PolySchnack-Transkriptions-Editor:
   mehrere eingeloggte Nutzer bearbeiten dieselbe Transkription
   gleichzeitig, konfliktfrei via CRDT (Yjs).
2. **Live-Sync + Awareness:** Änderungen erscheinen in Echtzeit bei allen
   Teilnehmern; fremde Cursor/Selektionen sind sichtbar; Undo/Redo und
   Offline-Toleranz (Änderungen werden bei Wiederverbindung gemerged).
3. **Export-Schnittstelle für Change 026:** Finalisieren einer
   Transkription liefert den Text je Segment (Klartext-Zeile je Segment)
   in dem Format, das `ownership.py accept` nach
   `transcripts/user/<sample>.txt` schreibt — keine manuelle Kopie mehr.
4. **Kein Eingriff in den Benchmark-Ownership:** Wer die finale Referenz
   besitzt und wann sie verbindlich wird, bleibt der Zustandsmaschinen-
   Workflow aus Change 026 (agent → proposed → user_owned). Der
   kollaborative Editor ist die **Eingabe-Oberfläche** dafür.

## Architektur (evaluierte Optionen)

- **CRDT-Bibliothek:** [Yjs](https://github.com/yjs/yjs) (MIT, konfliktfreie
  Shared Types `Y.Text`/`Y.Map`, Offline-Editing, Undo/Redo, Awareness;
  genutzt von Nextcloud, JupyterLab, Proton Docs).
- **Server:** `pycrdt-websocket` (Python, aktiv gepflegter Nachfolger des
  archivierten `ypy`; passt in den Python-Stack der Webapp). **UMGESETZT
  als ASGI-Mount `/yjs` in der Webapp selbst** (kein separater
  Compose-Dienst): same-origin → Session-Cookie funktioniert ohne CORS,
  ein Prozess/Container, Failover „Solo" bei fehlendem pycrdt im Image.
  Fallback-Option (später, falls Trennung nötig): hocuspocus/pycrdt als
  eigener Dienst — das WS-Interface (`/yjs/<room>`) bleibt gleich.
- **Room-Modell:** ein Yjs-Dokument je Transkription (Room-Key =
  Recording-UID), Segmente als `Y.Map<segment_index, Y.Text>` (ein
  `Y.Text` je Segment). Awareness-Update mit Nutzername + aktive Nutzer.
- **Auth (verifiziert):** Zwei Stufen im `on_connect`-Hook, konsistent zur
  Segment-Edit-Route: (1) gültige Session mit eingeloggtem User
  (`user_id` in der Session; anon → abgelehnt), (2) `write`-Zugriff auf
  die konkrete Recording (Owner oder per Share freigegeben, UID aus dem
  WS-Pfad). Kollaboration ist also **nur mit write-Freigabe** möglich.
- **Persistenz:** Length-prefixed Yjs-Update-Snapshots je Room als Datei
  (`DATA/yjs/<uid>.bin`): Voll-State beim ersten Start + Deltas per
  `doc.observe`; beim Laden werden die Blöcke **einzeln** angewandt
  (konkatenierte Updates verarbeitet Yjs nicht korrekt). Finalisieren
  schreibt zusätzlich in die bestehende `rec.segments`-Struktur.
- **Export:** Über die bestehende Route `PUT /api/recordings/{uid}/segments`
  (REQ-BENCH-033): Der „In DB speichern"-Button im Editor sammelt die
  Yjs-Texte und ruft `replace_segments` auf (DB + Versions-Snapshot);
  `ownership.py accept --text-from <export.json>` übernimmt den finalen
  Text nach `transcripts/user/<sample>.txt` (Zeile je Segment).

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Edit-Modus zeigt: Verbindungsstatus („● Kollaboration aktiv / ◌ verbinde… /
  Solo"), Anzahl der gleichzeitig bearbeitenden Nutzer (Awareness) und
  einen „In DB speichern"-Button (Finalisieren → `rec.segments` + Version).
- Speichern wird im Kollaborations-Modus durch Live-Sync ersetzt: Der
  Edit eines Segments geht sofort an alle Teilnehmer; die DB-Persistenz
  passiert beim Finalisieren. Ohne Verbindung fällt der Editor auf das
  bisherige Verhalten zurück (PATCH je Segment).
- Kein neuer Compose-Dienst: pycrdt läuft als ASGI-Mount in der Webapp
  (`/yjs`), Snapshot-Ordner `DATA/yjs/` im Webapp-Volume.
- `ownership.py accept --text-from <export.json>` übernimmt den finalen
  Text aus dem Editor-Export (statt manueller Datei-Erstellung).

## Abgrenzung / Ehrlichkeit

- CRDT garantiert **Konfliktfreiheit der Struktur** (keine verlorenen
  Änderungen), nicht inhaltliche Korrektheit — der Ownership-/Annahme-
  Workflow (026) bleibt die Qualitätskontrolle.
- Awareness ist ein Best-Effort-Feature (Verbindungsabbrüche möglich);
  die Textdaten sind davon unabhängig gesichert (Yjs-Snapshots).
- Die Box hat aktuell einen Ein-Container-Stack? Nein — Webapp + Backends
  als Compose-Services; der neue Sync-Dienst folgt dem bestehenden
  Compose-Muster (Port-Mapping, Healthcheck, Profile wie `ps-tor`).
- Betrieb ohne Sync-Dienst: Der Editor fällt auf Solo-Edit zurück
  (bestehendes Verhalten), keine Blockade.

## Specs-Delta

`ADDED` — REQ-BENCH-032 (Kollaborativer Edit-Modus: Live-Sync, Awareness,
Undo/Redo, Offline-Toleranz)
`ADDED` — REQ-BENCH-033 (Export-Schnittstelle: finalisierte Transkription
im Segment-Klartext-Format für Change 026)
