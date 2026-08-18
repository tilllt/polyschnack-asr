# Change 014 — Design

## Kontext

Drei unabhängige Befunde, ein gemeinsamer Nenner: Die Speicherschicht ist
flach und ohne Eigentümer-Konzept, und es gibt kein Selbstheilungs-Pfad für
„DB-Eintrag ohne gültige Datei".

## Entscheidungen

### 1. User-Ordner: `AUDIO_DIR/<user_id>/` statt flach

- **Ansatz:** Neuer Helfer `storage_path_for(user_id, ext)` → Unterordner pro
  User. `user_id` ist immer gesetzt (anon-Sessions haben eine ID), der
  anon-Ordner heißt `anon` (menschenlesbar, stabil).
- **Warum nicht migrieren:** Bestehende Dateien liegen flach; ein
  Migrations-Script müsste `stored_path` in der DB umschreiben (Risiko bei
  laufender Box ohne SSH-Zugriff). Stattdessen: Legacy bleibt gültig,
  neue Schreibvorgänge landen im User-Ordner; Re-Transcribe einer
  Legacy-Aufnahme zieht sie in den User-Ordner des aktuellen Users.
- **Alternative verworfen:** `stored_path` komplett relativ speichern —
  bricht bestehende Pfade und den Recovery-Restore.

### 2. Self-Healing: beide Richtungen

- `orphan_sweep.py` (bestehend): Datei ohne DB-Eintrag → löschen.
- Neu `recording_health.py`: DB-Eintrag ohne gültige Datei → `failed` +
  Fehlertext. Kein stilles Löschen von DB-Rows (Datenschutz-Kette:
  User soll sehen, was passiert ist, und selbst löschen).
- **Root Cause für „nicht löschbar":** `permissions.py` gibt für
  `user_id=None` nur `read`. Fix: `owner_user_id`-Spalte als Fallback;
  `recovery_restore` und der anon-Upload setzen sie. Alte Einträge ohne
  Owner: nur Admin löschbar (bewusst konservativ — niemand soll fremde
  Legacy-Aufnahmen löschen können, nur der Besitzer der Session, die sie
  erzeugt hat, oder Admins).

### 3. Titel + Sidecar

- DB-Spalte `title` ist die Quelle der Wahrheit (schnell, indexierbar,
  konsistent mit Versions-Snapshots).
- Sidecar `{stored_path}.meta.json` ist eine **denormalisierte Kopie** für
  Robustheit: Export/Re-Transcribe lesen es, wenn die DB nicht verfügbar
  ist (z.B. Wiederherstellung aus Datei-Backup). Schreib-Pfad: immer DB
  zuerst, dann Sidecar (best-effort, Fehler nur loggen).
- `original_name` bleibt unangetastet (Download-Dateiname, Upload-Herkunft).

## Offene Fragen

- Soll der Titel-Export (SRT/VTT-Dateiname) dem Titel folgen oder dem
  Dateinamen? → Aktuell: Dateiname (Req 3, unverändert). Bei Bedarf später
  ein Export-Prefix-Feld.
- Orphan-Ordner `anon`: Bei einer anon-Retention wird der komplette
  `anon/`-Ordner mit aufgeräumt? → Ja, über bestehende Retention-Logik
  (Eintrag + Datei + Sidecar).

## Trade-offs

- **User-Ordner vs. Migration:** Keine Umbau-Aktion an Alt-Daten, dafür
  zwei Pfad-Schemata parallel. Vertretbar, weil `stored_path` absolut in
  der DB steht und der Code nur „schreibe nach storage_path_for(...)" nutzt.
- **Markieren statt löschen:** `failed`-Status ist sichtbar und reversibel;
  ein Auto-Delete von DB-Rows wäre bei falsch-positivem Scan
  (Race mit laufendem Upload) gefährlich. `min_age`-Schutz wie im
  Orphan-Sweep bleibt.
