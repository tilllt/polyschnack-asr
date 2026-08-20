# Change 034 — Self-Healing: MP4/M4A/WebM fälschlich als „kaputt" (Magic-Fix)

## Problem

Der Health-Scan (`recording_health.py`, Change 014/023) markiert seit dem
Deploy des 19.08.-Images gesunde Aufnahmen als `status="failed"` mit
`unbekanntes Format (Magic: b'\x00\x00\x00\x1c')`. Ursache: Die Magic-Liste
enthielt `b"ftyp"` als **Präfix**-Check — echte MP4/M4A-Dateien (iOS-
Aufnahmen) beginnen aber mit der 4-Byte-Box-Größe (`\x00\x00\x00\x1c` = 28),
der Box-Typ `ftyp` steht erst an Position 4. `head.startswith(b"ftyp")`
matcht daher nie → **jede M4A-Datei gilt als „unbekanntes Format"**.
WebM/EBML (MediaRecorder Android/Chrome) fehlte komplett. Der Scan ist
seit 18.08. im Code, wurde aber erst mit dem gestrigen Image-Deploy auf der
Box aktiv → plötzliche Massen-Fehldiagnose („vorher heil" = vorher nie
geprüft).

## Ziel

1. MP4/M4A korrekt erkennen (Box-Typ an Position 4: `ftyp`/`moov`/`mdat`/…).
2. WebM/EBML und AAC-ADTS ergänzen (MediaRecorder-Formate).
3. **Selbstheilung:** Bereits fälschlich als `failed` markierte Recordings,
   deren Datei nach aktuellem Check gültig ist, werden beim nächsten Scan
   zurückgesetzt (`done` bei vorhandener Transkription, sonst `uploaded`).
   Echte Schäden (Datei fehlt, zu klein, keine Audio-Magic) bleiben `failed`.

## Entscheidungen

- Erkennung als eigene Funktion `_looks_like_audio(head)`: Präfix-Magic
  (RIFF/ID3/MP3-Frame/AAC-ADTS/OggS/fLaC/EBML) **oder** ISO-BMFF-Box-Typ
  an Byte 4–7.
- `#EXTM3U` aus der Magic-Liste entfernt (kein Audio-Container, bewusst
  vorher schon kommentiert).
- Heilen nur bei `error` mit Präfix „Audio-Datei fehlt oder ist beschädigt"
  UND jetzt gültiger Datei — kein Zurücksetzen anderer Fehler.
- Tests: M4A/WebM/AAC/WAV/MP3/OGG gültig; Box-Typ „XXXX" weiterhin
  „unbekanntes Format"; Fehldiagnose wird geheilt; echter Schaden bleibt.

## Nicht-Ziele

- Kein Löschen/Reparieren der Audio-Dateien selbst (Dateien sind intakt).
- Kein manuelles Korrektur-Skript nötig — der nächste reguläre Scan heilt.

## Deployment-Hinweis

Fix + Selbstheilung kommen mit dem nächsten Image-Build (CI bei Push).
Nach dem Deploy heilt der erste reguläre Health-Scan die fälschlich
markierten Recordings automatisch (kein Eingriff auf der Box nötig).
