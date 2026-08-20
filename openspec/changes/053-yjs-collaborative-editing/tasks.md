# Change 053 — Tasks

## Phase 1: Sync-Dienst (pycrdt-websocket)
- [ ] `pycrdt`/`pycrdt-websocket` als Compose-Dienst `ps-yjs-sync`
      (Dockerfile, Compose-Eintrag, Healthcheck, Profil wie `ps-tor`)
- [ ] Room-Modell: Room-Key = Recording-UID; Auth-Middleware prüft
      Session/Bearer gegen Webapp (nur eingeloggte Nutzer)
- [ ] Persistenz: Yjs-Snapshot je Room (SQLite/JSON), Restore beim
      Server-Neustart, Cleanup verwaister Rooms
- [ ] Awareness: Nutzername + Cursor-Position an Clients durchreichen

## Phase 2: Frontend (Yjs im Edit-Modus)
- [ ] `yjs` + WebSocket-Provider (z. B. `y-websocket`-Client) installieren
- [ ] SegmentList/Edit-Modus: Segmente als Yjs-Shared-Types laden
      (Fallback: Solo-Edit ohne Server-Kontakt)
- [ ] Awareness-Rendering: fremde Cursor/Selektionen + Namen anzeigen
- [ ] Undo/Redo (Yjs-UndoManager) + Verbindungsstatus-Badge
      (verbunden/synchronisiere/offline — ehrliche Status, kein Fake)

## Phase 3: Export-Brücke zu Change 026
- [ ] REST-Route `POST /api/recordings/{uid}/finalize` → Segment-Text
      (Klartext-Zeile je Segment), schreibt `rec.segments` final
- [ ] Format-Vertrag dokumentieren (Segment-Index → Zeile), Abgleich mit
      `ownership.py accept` (Import aus finalisierter Transkription)
- [ ] `ownership.py`: Option, finalisierten Editor-Text als Basis für
      `transcripts/user/<sample>.txt` zu übernehmen (statt manueller Datei)

## Phase 4: Tests + Qualität
- [ ] Backend-Tests: Room-Auth (401 ohne Login), finalize-Route
      (Format, Idempotenz), Snapshot-Restore
- [ ] Frontend-Tests: Edit-Modus mit Fake-Provider (Offline-Fallback,
      Awareness-Anzeige), tsc + bestehende Suiten grün
- [ ] CI grün melden, Deploy-Bundle 040–053 zusammenstellen
