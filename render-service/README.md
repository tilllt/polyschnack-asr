# Render-Dienst

Brennt `.ass`-Untertitel in ein Video ein (`burn_mp4`) oder erzeugt ein Untertitel-Video
**mit Alphakanal** für Schnitt- und Präsentationsprogramme (`hevc_alpha`, `screen_mp4`,
`chroma_mp4`, `alpha_webm`, `png_seq`, …). Läuft auf Port **8090**, kein GPU-Zwang,
`/health` meldet die tatsächlich verfügbaren Fähigkeiten (`x265_alpha`, `formats`, `fonts`).

Dieses Dokument erklärt **den ffmpeg-Bau mit Alpha-Unterstützung** und wie man diesen
Container als **Baustein für eigene (Multi-Stage-)Builds** benutzt, die Alphakanal-Support
brauchen.

---

## 1. Warum ein eigener ffmpeg-Bau überhaupt nötig ist

HEVC mit Alphakanal ist in freien Distributionen **nicht** enthalten. Drei Dinge müssen
zusammenkommen — jedes einzeln nachprüfbar:

1. **x265 mit `-DENABLE_ALPHA=ON` bauen.** Debian liefert libx265 ohne diese Option; die
   Option `alpha` ist dort nicht einmal registriert (gemessen über `x265_param_parse`:
   Debian `-1`, eigener Bau `0`).
2. **Die geteilte x265-Bibliothek plus eine `x265.pc` bereitstellen.** x265s CMake
   installiert nur die **statische** Bibliothek, die Header und das CLI — und **keine**
   pkg-config-Datei. ffmpeg braucht aber `PKG_CONFIG_PATH` mit einer `x265.pc`, sonst
   bindet es x265 nicht ein.
3. **ffmpeg mit `-DX265_ENABLE_ALPHA` konfigurieren und aus einem Quellstand ≥ 8.0 bauen.**
   Der Alpha-Pfad im libx265-Wrapper steht hinter
   `#if defined(X265_ENABLE_ALPHA) && MAX_LAYERS > 2`. FFmpeg **7.1 hat ihn nicht**,
   ab **8.0** ist er drin. ffmpegs `configure` setzt dieses Define nirgends — deshalb ist
   auch ein Standardbau ab 8.0 **ohne** HEVC-Alpha, solange man den Schalter nicht mitgibt.
   Merkmal eines korrekten Baus: `ffmpeg -h encoder=libx265` listet **`yuva420p`**.

## 2. Wo der Bau liegt

- `ffalpha-build/Dockerfile` — baut x265 + ffmpeg aus Quellen und prüft im Bau, dass eine
  echte Alpha-Aufnahme entsteht und sich wieder auslesen lässt. Dauer **15–20 Minuten**.
- Ergebnis-Image: `harbor.rand0m.me/public/polyschnack-asr-ffalpha:v1` — bewusst ein
  **selten gebautes** Image mit fester Version. **Version erhöhen = neu bauen.**
- Der CI-Job dazu (`build-ffalpha`) braucht `tags: [shared]`; ohne Tag bleibt er pending,
  weil der Projekt-Runner keine untagged Jobs annimmt.
- Der Alpha-Bau selbst wird hier **nicht** dupliziert: Das Render-Image kopiert nur
  `/opt/ffalpha` aus diesem Image. Wer den Bau nachvollziehen will, liest
  `ffalpha-build/Dockerfile` — dort stehen alle drei Bedingungen mit Begründung.

## 3. Was dieses Image daraus macht

```
COPY --from=harbor.rand0m.me/public/polyschnack-asr-ffalpha:v1 /opt/ffalpha /opt/ffalpha
```

Danach gilt im Container:

- **Es gibt genau ein ffmpeg**, und zwar das Alpha-Build:
  `/usr/local/bin/ffmpeg`, `/usr/local/bin/ffprobe`, `/usr/local/bin/x265` sind Symlinks auf
  `/opt/ffalpha/bin/*`. `/usr/local/bin` steht in PATH vor `/usr/bin` — ein beliebiger
  Aufruf `ffmpeg …` trifft also das fähige Binary, ohne Sonderpfad.
  Das Debian-Paket `ffmpeg` wird **absichtlich nicht** installiert: es kann kein
  HEVC-Alpha und wäre ein zweites Binary unter `/usr/bin`.
  Messung dazu: `ldd /opt/ffalpha/bin/ffmpeg` → 0 fehlende Bibliotheken und **keine**
  `libavcodec`/`libavformat`/`libavutil`-Abhängigkeit; das Alpha-ffmpeg ist statisch gegen
  seine eigenen libav\* gebaut. Es braucht nur die externen Codec-/Font-Bibliotheken
  (`libass9 libfreetype6 libfontconfig1 libfribidi0 libharfbuzz0b libvpx9 libx264-164 zlib1g`).
- `RENDER_FFMPEG=/opt/ffalpha/bin/ffmpeg`, `RENDER_FFPROBE=/opt/ffalpha/bin/ffprobe` sind
  gesetzt (explizit statt implizit) — der Dienst hängt nicht davon ab, wie PATH aussieht.
- `LD_LIBRARY_PATH=/opt/ffalpha/lib` — damit findet die **x265-CLI** ihre geteilte
  Bibliothek auch ohne Prefix-Pfad. Das ffmpeg selbst hat den Pfad als rpath einkompiliert.

Der Bau **erzwingt** diese Ordnung (und bricht sonst ab):

- `ffmpeg` im PATH muss auf `/usr/local/bin` zeigen,
- dieses ffmpeg muss `yuva420p` können,
- unter `/usr/bin/ffmpeg` darf **kein** zweites Binary liegen,
- libass-Filter und die Encoder `libx264 libvpx-vp9 prores_ks png libx265` müssen da sein,
- Arial muss auf Liberation Sans aufgelöst werden (`fc-match`).

Nebeneffekt der Umstellung (Change 204): Das Render-Image schrumpfte von **738 MB auf
**319 MB**, weil die `libav*`-Bibliotheken des Debian-Pakets entfallen.

## 4. Diesen Container als Baustein für eigene Builds benutzen

Zwei Wege, je nachdem, was man braucht:

**A) ffmpeg mit Alpha im PATH, eigener Anwendungs-Container** — das Render-Image als Stage:

```dockerfile
FROM harbor.rand0m.me/public/polyschnack-asr-render:latest AS ffmpeg_alpha
# ffmpeg / ffprobe / x265 liegen hier bereits als Standard im PATH
FROM debian:trixie-slim
COPY --from=ffmpeg_alpha /opt/ffalpha /opt/ffalpha
COPY --from=ffmpeg_alpha /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg_alpha /usr/local/bin/ffprobe /usr/local/bin/ffprobe
# Die Symlinks zeigen auf /opt/ffalpha/bin/* — die Laufzeit-Bibliotheken mitnehmen:
RUN apt-get update && apt-get install -y --no-install-recommends \
      libass9 libfreetype6 libfontconfig1 libfribidi0 libharfbuzz0b \
      libvpx9 libx264-164 zlib1g ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -hide_banner -h encoder=libx265 | grep -q yuva420p \
    && echo "ffmpeg mit HEVC-Alpha bereit"
```

**B) Nur die Binaries, ohne Debian-Basis** — direkt aus dem Bau-Image:

```dockerfile
COPY --from=harbor.rand0m.me/public/polyschnack-asr-ffalpha:v1 /opt/ffalpha /opt/ffalpha
RUN ln -sf /opt/ffalpha/bin/ffmpeg /opt/ffalpha/bin/ffprobe /usr/local/bin/ \
 && ldconfig
```

**C) Alles selbst bauen** (kein Zugriff auf die interne Registry): Inhalt von
`ffalpha-build/` nehmen und dort bauen —

```sh
docker build -t ffmpeg-alpha:local ffalpha-build/
docker run --rm ffmpeg-alpha:local ffmpeg -hide_banner -h encoder=libx265 | grep yuva420p
```

> **Hinweis für Fremde/Forks:** In `render-service/Dockerfile` steht die interne Registry
> fest in der `COPY --from=`-Zeile. Ohne Zugriff darauf ist Weg A/B nicht baubar — dann
> Weg C nehmen und die `COPY --from=`-Zeile auf das eigene Tag umstellen.

## 5. Wie man Alphakanal nachweist (statt ihn zu vermuten)

```sh
# 1. Kann dieses ffmpeg Alpha überhaupt?
ffmpeg -hide_banner -h encoder=libx265 | grep yuva420p

# 2. Echte Aufnahme erzeugen (transparenter Hintergrund + Text)
ffmpeg -y -f lavfi -i "color=c=black@0.0:s=640x360:r=25:d=2,format=yuva420p" \
       -vf "ass=subs.ass:alpha=1" -c:v libx265 -pix_fmt yuva420p -tag:v hvc1 out.mp4

# 3. Alpha numerisch messen — Alpha-Mittel und -Maximum im Bereich X/Y/W/H
ffmpeg -v error -i out.mp4 -vf "crop=W:H:X:Y,alphaextract,format=gray,signalstats,\
metadata=print:key=lavfi.signalstats.YAVG:file=-" -frames:v 1 -f null -
```

Drei Fallen, die dabei schon zugeschlagen haben:

- **`ffprobe` meldet `yuv420p`, obwohl Alpha drin ist.** Der Kanal liegt als eigene Ebene
  vor. Nicht auf `pix_fmt` prüfen, sondern den Alphakanal **auslesen**.
- **`format=gray` gehört zwingend dazu.** Ohne es liefern 10/12-Bit-Ebenen Werte weit über
  255 (z. B. 3773) und die Zahl ist unbrauchbar.
- **Leere Messung ≠ Skriptfehler:** `alphaextract` scheitert still, wenn der dekodierte
  Strom gar kein Alpha hat. Gegenprobe: ein Kontrollfenster muss 0 liefern.

## 6. HEVC-Alpha im Bitstrom (Kurzfassung)

Für Apple-kompatible Ausgabe (QuickTime, Keynote, iOS, KineMaster 7.1+) muss die
Signalisierung stimmen:

- Der **VPS-Extension**-Block muss die Alpha-Ebene als **AUX (AuxId = 1)** ausweisen
  (`scalability_mask` mit dem AUX-Bit). Stock-x265 setzt zusätzlich den SPATIAL-Typ
  (`0x3000`); Apples eigener Encoder und unsere Apple-Referenzdateien setzen **nur** AUX
  (`0x1000`).
- Die **SEI-Nachricht 165** (`alpha_channel_information`) trägt `use_idc`
  (0 = straight, 1 = premultiplied), `transparent`/`opaque` und Clipping-Hinweise.
- Im MP4 muss der `hvcC` **beide Schichten** tragen: 1× VPS Layer 0, je 2× SPS/PPS für
  Layer 0 und 1. Sample-Entry `hvc1`.
- Die Apple-Hülle `muxa`/`almo` ist **nicht** erforderlich: Apples eigene Referenzdatei von
  2019 hat beides nicht und spielt trotzdem.

Notizen und Messreihen dazu: `openspec/changes/204-ein-ffmpeg-im-render-image/` sowie die
zugehörige Skill-Dokumentation zum x265-Alpha-Patch.

## 7. Betrieb

| Variable | Zweck |
| --- | --- |
| `RENDER_FFMPEG` / `RENDER_FFPROBE` | zu benutzende Binaries (im Image auf `/opt/ffalpha/bin/*` gesetzt) |
| `RENDER_DATA` | Arbeitsverzeichnis für Jobs (Standard `/data/render`) |
| `RENDER_TTL_S` | Aufbewahrung fertiger Ergebnisse |
| `RENDER_TIMEOUT_S` | Abbruchgrenze je Job |

Betriebliche Fallstricke:

- Der Dienst hängt in einem Compose-**Profil** (`profiles: ["render"]`). Ein
  `docker compose up -d ps-render` **ohne `--profile render` überspringt ihn still**.
- Der Container läuft als **uid 10001 (`render`)** — gemountete Verzeichnisse müssen ihm
  gehören.
- `curl` ist im Image vorhanden (der Healthcheck braucht es).

---

*Diese Datei ist Teil von Change 204 („Ein ffmpeg im Render-Image") und beschreibt den
Stand vom 19.09.2026.*
