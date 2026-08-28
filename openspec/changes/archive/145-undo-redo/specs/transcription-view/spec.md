## MODIFIED Requirements

### Requirement: Text-Edit (Erzwungener Sync)

- **Ergänzung (Change 145):** Undo/Redo über einen lokalen Stack (max.
  50 Snapshots), Push nur nach Server-Bestätigung. Buttons in der
  Transkriptions-Kopfzeile + Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y außerhalb
  von Eingabefeldern. Neue Aktion invalidiert Redo. Stack ist
  session-lokal (Option B, Server-gestützt, bleibt offen).
