# Change 206 — Original-Audio-Download liefert eine brauchbare Datei

## Warum

Aus dem Menü der Aufnahme („AUD — Original-Aufnahme") lud der Nutzer die Originaldatei herunter
und bekam etwas, mit dem er nichts anfangen konnte. Die Anfrage selbst war in Ordnung
(`GET /api/recordings/{uid}/audio` → 200), die **Auslieferung** war falsch:

1. Der **Dateiname** war der Anzeigename der Aufnahme — und der trägt bei konvertierten Dateien
   eine Notiz: `recording_1789746763803.webm (konvertiert von .webm nach MP3)`. Als
   `Content-Disposition`-Dateiname geschickt, landet die Datei damit **ohne brauchbare Endung** auf
   dem Gerät (`.webm (konvertiert von .webm nach MP3)`) — Handy, Messenger und Schnittprogramme
   erkennen sie nicht.
2. Der **Content-Type** folgte dem DB-Feld `mime`, das nach einer Konvertierung auf dem alten Wert
   stehen bleibt (`audio/wav`), obwohl auf der Platte eine **MP3** liegt.

Beides zusammen: eine heruntergeladene Datei, die sich nicht öffnen lässt — für den Nutzer „geht
nicht".

## Was sich ändert

1. **Download-Name** (`_download_name`): Anzeigename ohne die Konvertier-Notiz, aber mit der Endung
   der **tatsächlich abgelegten** Datei. Aus
   `recording_1789746763803.webm (konvertiert von .webm nach MP3)` wird
   `recording_1789746763803.mp3`. Namen mit Punkten/Leerzeichen (`18. Sept. um 12-31.m4a`) bleiben
   erhalten.
2. **Content-Type** (`_guess_mime`): Die Endung der abgelegten Datei gewinnt, das DB-Feld ist nur
   noch Rückfall. Damit liefert eine MP3 auch `audio/mpeg`.
3. Tests: `tests/test_download_original_audio.py` (Namenslogik, Punkte/Leerzeichen, fehlende Endung,
   MIME-Vorrang, plus der volle Weg über den Endpunkt).

## Abgrenzung

- Nur die Auslieferung. Der Anzeigename in der Oberfläche (mit Notiz) bleibt — die Notiz ist dort
  sinnvoll und informativ.
- Die Notiz wird **nicht** rückwirkend aus der Datenbank entfernt (keine Migration).
- `audio/preview` (Player-Streaming) bleibt unverändert; es liefert ohne `attachment`.
