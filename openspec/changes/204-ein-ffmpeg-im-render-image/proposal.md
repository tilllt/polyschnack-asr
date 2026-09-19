# Change 204 — Ein ffmpeg im Render-Image: das Alpha-Build als Standard

## Warum

Im Render-Image lagen **zwei** ffmpeg-Versionen:

- `/usr/bin/ffmpeg` — aus dem Debian-Paket `ffmpeg` (7.1.5), **kann kein HEVC-Alpha**
- `/opt/ffalpha/bin/ffmpeg` — der eigene Bau (8.0, `-DX265_ENABLE_ALPHA`), benutzt vom
  Dienst über `RENDER_FFMPEG`

Der Dienst selbst griff immer zum richtigen Binary. **Jeder andere Aufruf** im Container traf
aber die alte Version: Ad-hoc-Arbeit, Werkzeuge, Skripte. Genau das ist am 19.09.2026 beim Bau
der Alpha-Testdateien passiert — `ffmpeg` im Container lehnte den Alpha-Strom mit
„Scalability type 1 not supported" ab, obwohl das fähige Binary zwei Verzeichnisse weiter lag.

Zwei Versionen sind hier keine Reserve, sondern eine Falle, und der Container ist so auch nicht
als allgemeine ffmpeg-Schicht benutzbar (`docker run … ffmpeg …` schlägt fehl bzw. kann weniger
als erwartet).

## Was sich ändert

1. Das Debian-Paket `ffmpeg` wird **nicht mehr installiert**. Stattdessen die
   Laufzeit-Bibliotheken, die das Alpha-Build braucht. Das ist belegt, nicht geraten: `ldd` im
   Container zeigt, dass das Alpha-ffmpeg **statisch** gegen seine eigenen `libav*` gebaut ist —
   vom Debian-Paket braucht es nichts (0 fehlende Bibliotheken, keine `libav*`-Abhängigkeit).
2. `/usr/local/bin/ffmpeg`, `/usr/local/bin/ffprobe` und `/usr/local/bin/x265` werden
   **Symlinks** auf das Alpha-Build. `/usr/local/bin` steht in PATH vor `/usr/bin`, damit trifft
   jeder Aufruf ohne vollen Pfad das fähige Binary.
3. `LD_LIBRARY_PATH=/opt/ffalpha/lib` — die x265-CLI findet ihre geteilte Bibliothek so auch
   ohne Prefix-Pfad; das ffmpeg hat sein rpath einkompiliert.
4. Die Bau-Prüfung wird **verschärft**: Der Build bricht ab, wenn
   - `ffmpeg` im PATH nicht auf `/usr/local/bin` zeigt,
   - dieses ffmpeg kein `yuva420p` kann, oder
   - unter `/usr/bin/ffmpeg` noch ein zweites Binary liegt.

## Abgrenzung

- **Kein** Umbau des ffalpha-Baus (`ffalpha-build/`, Image `:v1` bleibt wie er ist). Der
  Render-Image-Bau kopiert weiterhin aus diesem Image; die Version dort erhöhen heißt: neu bauen.
- `RENDER_FFMPEG`/`RENDER_FFPROBE` bleiben **gesetzt** — explizit ist besser als implizit, und
  der Dienst soll nicht davon abhängen, wie PATH gerade aussieht.
- Keine Änderung an Render-Logik, API, Formaten oder Oberfläche.
