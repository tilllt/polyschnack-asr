# Status — Change 204

**Stand 19.09.2026:** Dockerfile umgebaut, Pre-Check-Bau läuft.

## Belege

- Zwei Binaries im laufenden Container: `/usr/bin/ffmpeg` = 7.1.5 (Debian-Paket),
  `/opt/ffalpha/bin/ffmpeg` = n8.0 (eigener Bau), beide per `-version` belegt.
- Anlass: `ffmpeg` im Container lehnte den Alpha-Rohstrom ab („Scalability type 1 not
  supported"), während `/opt/ffalpha/bin/ffmpeg` ihn verarbeiten konnte.
- Bibliotheksmessung: `ldd /opt/ffalpha/bin/ffmpeg` → 0 fehlende Bibliotheken, keine
  `libav*`-Abhängigkeit vom Debian-Paket.

## Offen

- Pre-Check-Bau auf der KI-Box (Ergebnis siehe unten, sobald vorhanden).
- CI-Bau + Harbor, Deploy des Render-Dienstes, Live-Abnahme.

## Nachzutragen nach der Abnahme

- Image-Digest/Revision, Ergebnis der Prüfungen im Container, `/health`-Antwort und Messwerte
  eines Live-Renders (Alpha deckend/transparent).
