# Aufgaben — Change 204

- [x] Ursache belegt: zwei ffmpeg-Binaries im Image (`/usr/bin/ffmpeg` 7.1.5 aus dem
      Debian-Paket, `/opt/ffalpha/bin/ffmpeg` 8.0) — Beleg: `dpkg -l ffmpeg`,
      `ls -la /opt/ffalpha/bin`, Canary-Decode des Alpha-Rohstroms.
- [x] Abhängigkeiten gemessen: `ldd /opt/ffalpha/bin/ffmpeg` ohne `not found`, ohne `libav*`
      → Debian-Paket nicht nötig.
- [x] Dockerfile: Paket `ffmpeg` durch die Laufzeit-Bibliotheken ersetzt.
- [x] Dockerfile: Symlinks `/usr/local/bin/{ffmpeg,ffprobe,x265}` → `/opt/ffalpha/bin/*`.
- [x] Dockerfile: `LD_LIBRARY_PATH=/opt/ffalpha/lib`.
- [x] Dockerfile: Bau-Prüfung um „PATH-ffmpeg ist das Alpha-Build" und „kein zweites
      `/usr/bin/ffmpeg`" erweitert.
- [x] `render-service/README.md` geschrieben: Alpha-ffmpeg-Bau (drei Bedingungen, gemessene
      Fakten), Nutzung des Images/Containers als Baustein für eigene Multi-Stage-Builds
      (drei Wege, inkl. Hinweis auf die fest verdrahtete interne Registry), Alpha-Nachweis
      mit Messbefehlen und Fallstricken, Kurzfassung der Bitstrom-Signalisierung, Betrieb.
- [x] Image bauen (Pre-Check auf der KI-Box) und im Container prüfen: `command -v ffmpeg`
      → `/usr/local/bin/ffmpeg`, `ffmpeg -version` → n8.0, `-h encoder=libx265` zeigt
      `yuva420p`, `/usr/bin/ffmpeg` fehlt, echte Alpha-Aufnahme mit dem **Standard**-Aufruf
      (Muxen + `alphaextract` = 134,752). Image 738 MB → 319 MB.
- [x] Über CI bauen lassen (Harbor): Pipeline #5394, `build-render` 55 s grün,
      `mirror-github` grün.
- [x] Render-Dienst mit allen vier Compose-Overlays plus `--profile render` neu starten;
      Revision `2cbd40cb`, Container gesund, `/health` = `ok`.
- [x] Funktionsnachweis im laufenden Container: Alpha-Untertitelvideo über den Dienstpfad
      (ass + libx265) erzeugt, x265-Werkzeugliste enthält `alpha`, Transparenz gemessen
      (Mittel 7,92).

