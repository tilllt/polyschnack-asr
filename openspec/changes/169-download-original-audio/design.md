# Change 169 — Design

## Warum kein neuer Endpoint

`get_audio` erfüllt bereits alles: Original-Datei (nicht die 64-kbps-
Preview), `filename=original_name` (Content-Disposition attachment),
Range-Support (der Player nutzt dieselbe URL) und 410 bei fehlender Datei
(GUI zeigt den Defekt-Badge). Ein separater „download"-Endpoint wäre
Duplikat.

## Zugriffsmodell

`ensure_access(..., \"read\")` — dieselbe Schwelle wie das Playback.
Wer die Aufnahme hören darf, darf sie auch herunterladen (konsistent;
der Backup-ZIP bleibt full/owner-exklusiv, weil er die kompletten
Metadaten enthält).

## Frontend-Platzierung

Eintrag direkt nach den Export-Formaten, vor dem full/owner-ZIP-Block —
sichtbar für alle Zugriffsstufen, kein Trenner nötig (Audio ist ein
Export wie die Formate).

## Offene Fragen

Keine. Dateiname kommt vom Server (original_name) — das `download`-
Attribut ohne Wert respektiert den Content-Disposition-Filename.
