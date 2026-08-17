## MODIFIED Requirements

### Requirement: Queue-API (Recording-Karte kennt Position + Warte-ETA)

- **Ablauf:** `GET /api/queue` bleibt wie bisher (Watcher). Zusätzlich
  liefert die Recording-Serialisierung (`_recording_to_dict` in
  `routers/recordings.py`) für `status == "queued"` (und laufende Jobs mit
  Warteschlange davor):
  - `queue_position: int` — 1 + Anzahl vorausgehender queued Jobs auf
    demselben Backend (`queue_manager.position(rec.id)`, Queue-Regeln wie
    Req 3: Priorität, dann FIFO).
  - `queue_eta_s: Optional[int]` — `round(position × avg_recent_processing_ms
    / 1000)`, `None` wenn keine Statistik.
  - `queue_backend: str` — Backend-Name (für die Anzeige).
- **Heartbeat/Phasen-Zeitstempel:** `progress_pct`/`progress_note` werden
  ergänzt um `phase_started_at` und `last_heartbeat_at` (ISO-Strings,
  `null` bis gesetzt). Jeder `set_progress`-Aufruf aktualisiert
  `last_heartbeat_at`; ein Phasenwechsel (neue `note`) setzt
  `phase_started_at`. Damit kann die UI „läuft, aber kein messbarer
  Fortschritt" von „eingefroren/hängend" unterscheiden.
- **Architektur:** `crud.set_progress` (Heartbeat + Phasenwechsel),
  `queue.py` (Position, unverändert), `routers/recordings.py`
  (`_recording_to_dict`), `models.py` (2 neue Felder, Auto-Migration).

#### Scenario: Nutzer sieht Warteposition auf der Karte

- **Akteure:** Registrierter User mit Aufnahme in der Warteschlange.
- **Eingaben:** Zwei Jobs auf demselben Backend; der eigene Job ist an
  Position 2; durchschnittliche Verarbeitung 90 s.
- **Ergebnis:** Die Karte zeigt „Warteschlange · Position 2 · ~2m" und
  keinen Spinner — `queue_position=2`, `queue_eta_s=180`.

#### Scenario: Kein Fortschritt, aber Job lebt (Heartbeat)

- **Akteure:** Besitzer einer Aufnahme in Sync-ASR (CrispASR, kein
  Job-Progress).
- **Eingaben:** `progress_pct` bleibt 21; `last_heartbeat_at` wird alle
  5 s aktualisiert.
- **Ergebnis:** UI zeigt Puls + „transcribing · aktiv seit 3m" statt
  eingefrorenem „21% …".
