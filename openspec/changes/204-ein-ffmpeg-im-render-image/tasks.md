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
- [ ] Image bauen (Pre-Check auf der KI-Box) und im Container prüfen:
      `command -v ffmpeg`, `ffmpeg -version`, `-h encoder=libx265` zeigt `yuva420p`,
      `/usr/bin/ffmpeg` fehlt, echte Alpha-Aufnahme mit dem **Standard**-Aufruf.
- [ ] Über CI bauen lassen (Harbor), Image auf die KI-Box ziehen.
- [ ] Render-Dienst mit allen vier Compose-Overlays neu starten, `/health` zeigt `x265_alpha`.
- [ ] Live-Render prüfen (Alpha-Ausgabe mit Transparenz messen).
