# Status — Change 204

**Stand 19.09.2026: umgesetzt, gebaut, deployt und im Betrieb nachgewiesen.**

## Belege

- Zwei Binaries im laufenden Container: `/usr/bin/ffmpeg` = 7.1.5 (Debian-Paket),
  `/opt/ffalpha/bin/ffmpeg` = n8.0 (eigener Bau), beide per `-version` belegt.
- Anlass: `ffmpeg` im Container lehnte den Alpha-Rohstrom ab („Scalability type 1 not
  supported"), während `/opt/ffalpha/bin/ffmpeg` ihn verarbeiten konnte.
- Bibliotheksmessung: `ldd /opt/ffalpha/bin/ffmpeg` → 0 fehlende Bibliotheken, keine
  `libav*`-Abhängigkeit vom Debian-Paket.
- **Pre-Check-Bau auf der KI-Box:** Prüfkette meldet „Render-Image OK: libass + alle Encoder +
  HEVC-Alpha + Arial-Ersatz vorhanden"; im Container `command -v ffmpeg` →
  `/usr/local/bin/ffmpeg`, `ffmpeg -version` → n8.0, `/usr/bin/ffmpeg` nicht vorhanden,
  Alpha-Arbeit mit dem **Standardaufruf** (Muxen + `alphaextract`: Mittel 134,752).
  Image-Größe 738 MB → **319 MB**.
- **CI:** Pipeline #5394 (Commit `2cbd40cb`, aktueller HEAD) — `test-render` 104 s und
  `build-render` 55 s grün, Image in Harbor; `mirror-github` grün.
- **Deploy:** `ps-render` mit allen vier Overlays plus `--profile render` neu erstellt;
  Revision im Image `2cbd40cb`, Container gesund, `/health` = `ok` mit `libass` und der
  Formatliste.
- **Nachweis im laufenden Dienst-Container:** `ffmpeg` → `/usr/local/bin/ffmpeg` (n8.0),
  `/usr/bin/ffmpeg` fehlt; Alpha-Untertitelvideo über den Dienstpfad (ass + libx265) erzeugt
  (10.096 B), x265-Werkzeugliste enthält `alpha`, `alphaextract` misst Mittel 7,92
  (Text deckend, Umfeld transparent).
- Struktur der erzeugten MP4s (getrennt geprüft): `hvcC` mit VPS 1× Layer 0 und SPS/PPS je 2×
  für Layer 0/1, Sample-Entry `hvc1`, Alpha-SEI in den Samples.

## Dokumentation

- `render-service/README.md` — Alpha-ffmpeg-Bau (die drei Bedingungen), Nutzung als Baustein
  für eigene Multi-Stage-Builds (drei Wege), Alpha-Nachweis mit Messbefehlen und Fallstricken,
  Kurzfassung der Signalisierung, Betrieb.
- `docs/caption-export.md` — Verweis auf diese README plus die zwei Betriebspunkte.

## Offen (nicht Teil dieses Changes)

- Betriebs-Fallstrick dokumentiert: Der Dienst hängt in einem Compose-Profil; ohne
  `--profile render` überspringt `up -d ps-render` ihn still.

