# Design — Change 204

## Entscheidung: Debian-Paket entfernen **und** Symlink im PATH

Beides zusammen, nicht eines allein:

- Nur Symlink, Paket bleibt → das zweite Binary liegt weiter im Image. Es ist dann zwar nicht
  mehr der Standard, aber es bleibt da und wird über `/usr/bin/ffmpeg` weiterhin erreichbar
  sein. Genau diese Falle soll verschwinden.
- Nur Paket entfernen → `ffmpeg` wäre gar nicht mehr im PATH; jeder Aufruf müsste den vollen
  Pfad `/opt/ffalpha/bin/ffmpeg` kennen. Der Container wäre weiterhin keine allgemeine
  ffmpeg-Schicht.

Deshalb: Paket raus, Symlinks in `/usr/local/bin` (liegt in Debian/python-Images vor `/usr/bin`
in PATH), und die Bau-Prüfung erzwingt beides.

## Warum Symlinks statt Kopie oder PATH-Umbau

| Variante | Bewertung |
| --- | --- |
| Symlink in `/usr/local/bin` (gewählt) | 40 Byte, ein Binary bleibt die einzige Quelle der Wahrheit, Debian-Konvention (`/usr/local` gehört dem Administrator) |
| Binaries kopieren | Zwei Kopien von je 30 MB, die auseinanderlaufen können — genau das Problem, das dieser Change behebt |
| `ENV PATH=/opt/ffalpha/bin:$PATH` | Funktioniert für Shell-Aufrufe mit gesetzter Umgebung, aber nicht für Container-Aufrufe wie `docker run image ffmpeg …` bzw. für Prozesse mit eigener PATH-Erwartung; außerdem überschreibt es den PATH der Basis und verdeckt Systemwerkzeuge |
| `update-alternatives` | Dasselbe Ergebnis, aber mehr Maschinerie; in Containern ohne Not |

## Ist das Entfernen des Pakets sicher?

Gemessen im laufenden Container (`polyschnack-ps-render-1`, 19.09.2026):

- `ldd /opt/ffalpha/bin/ffmpeg` → keine `not found`-Einträge, **keine** `libavcodec`/`libavformat`/
  `libavutil`/`libswscale`-Zeilen: das Alpha-ffmpeg bringt seine libav\* selbst mit.
- Gegenprobe: das Debian-Paket liefert nur `/usr/bin/{ffmpeg,ffplay,ffprobe,qt-faststart}` — also
  reine Programme, keine Bibliotheken, die etwas anderes braucht.
- Der Dienst benutzt `RENDER_FFMPEG`/`RENDER_FFPROBE`; im Image gibt es keinen festen Aufruf von
  `/usr/bin/ffmpeg` (geprüft: `grep -rn "/usr/bin/ffmpeg" render-service/` → kein Treffer).

**Nebeneffekt:** das Image wird kleiner (die `libav*`-Bibliotheken des Debian-Pakets entfallen).

## Restrisiko

Wenn das Alpha-ffmpeg eine Bibliothek braucht, die bisher nur als Abhängigkeit des Debian-Pakets
im Image lag, schlägt der Bau fehl (nicht erst der Betrieb): die Prüfungen im Build kodieren
eine echte Alpha-Aufnahme (`yuva420p`-Formatliste, libass-Filter, alle Encoder) und laufen mit
`set -e`. Zusätzlich wird nach dem Umbau eine echte Alpha-Datei im Container erzeugt und
zurückgelesen.
