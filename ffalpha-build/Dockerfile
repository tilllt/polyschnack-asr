# ==============================================================
# ffmpeg mit HEVC-Alpha (fuer den Render-Dienst, Change 200)
# ==============================================================
# Warum ein eigenes Image: ffmpeg mit Alpha-Unterstuetzung muss selbst gebaut
# werden. Drei Dinge muessen zusammenkommen, jedes einzeln gemessen:
#
#   1. x265 mit -DENABLE_ALPHA=ON bauen. Debian baut libx265 ohne — die
#      Option `alpha` ist dort nicht einmal registriert (gemessen ueber
#      x265_param_parse: Debian -1, eigener Bau 0).
#   2. Die geteilte x265-Bibliothek ins Prefix legen und eine x265.pc
#      schreiben: x265s CMake installiert nur die STATISCHE Bibliothek,
#      die Header und das CLI — und gar keine pkg-config-Datei.
#   3. ffmpeg aus Quellen MIT Alpha-Code im Encoder bauen (7.1 hat ihn nicht,
#      ab 8.0 ist er drin: `#if defined(X265_ENABLE_ALPHA) && MAX_LAYERS > 2`)
#      und beim configure -DX265_ENABLE_ALPHA mitgeben. Ohne diesen Schalter
#      fehlt `yuva420p` in der Formatliste — ffmpegs configure setzt ihn
#      nirgends, deshalb hat auch ein Standardbau kein HEVC-Alpha.
#
# Der Bau dauert ~15-20 Minuten und gehoert deshalb NICHT in jeden Build des
# Render-Images, sondern in dieses selten gebaute Image (Tag :v1). Der
# Render-Container kopiert daraus /opt/ffalpha.
# ==============================================================
FROM python:3.12-slim AS build

#: x265-Quellstand. Ab 4.0 kann x265 Alpha (mit ENABLE_ALPHA).
ARG X265_REF=b81f650
#: ffmpeg-Release MIT Alpha-Unterstuetzung im libx265-Encoder (7.1 hat sie nicht).
ARG FFMPEG_REF=n8.0

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake pkg-config nasm curl git ca-certificates \
      libass-dev libfreetype-dev libfontconfig-dev libfribidi-dev libharfbuzz-dev \
      libvpx-dev libx264-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------- 1) x265
RUN git clone https://bitbucket.org/multicoreware/x265_git.git /src/x265 \
    && cd /src/x265 && git checkout ${X265_REF} \
    && cmake -S source -B build/linux -DCMAKE_BUILD_TYPE=Release -DENABLE_ALPHA=ON \
        -DCMAKE_INSTALL_PREFIX=/opt/ffalpha -DCMAKE_INSTALL_LIBDIR=lib \
    && cmake --build build/linux -j"$(nproc)" \
    && cmake --install build/linux \
    && grep -q "define ENABLE_ALPHA 1" /opt/ffalpha/include/x265_config.h \
    && echo "x265 mit Alpha gebaut"

# Geteilte Bibliothek + selbst geschriebene pkg-config-Datei (siehe Kopf).
RUN cp -a /src/x265/build/linux/libx265.so.* /opt/ffalpha/lib/ \
    && ln -sf "$(basename "$(ls /opt/ffalpha/lib/libx265.so.* | head -1)")" /opt/ffalpha/lib/libx265.so \
    && mkdir -p /opt/ffalpha/lib/pkgconfig \
    && printf '%s\n' \
        'prefix=/opt/ffalpha' \
        'libdir=${prefix}/lib' \
        'includedir=${prefix}/include' \
        '' \
        'Name: x265' \
        'Description: H.265/HEVC encoder (ENABLE_ALPHA)' \
        'Version: 4.1' \
        'Libs: -L${libdir} -lx265' \
        'Libs.private: -lstdc++ -lm -lrt -ldl -lnuma' \
        'Cflags: -I${includedir}' \
        > /opt/ffalpha/lib/pkgconfig/x265.pc \
    && test -f /opt/ffalpha/lib/libx265.so \
    && PKG_CONFIG_PATH=/opt/ffalpha/lib/pkgconfig pkg-config --exists x265 \
    && echo "x265 installiert + pkg-config vorhanden"

# ---------------------------------------------------------------- 2) ffmpeg
RUN git clone --depth 1 --branch ${FFMPEG_REF} \
      https://github.com/FFmpeg/FFmpeg.git /src/ffmpeg \
    && grep -q "X265_ENABLE_ALPHA" /src/ffmpeg/libavcodec/libx265.c \
    && echo "Quellstand ${FFMPEG_REF} enthaelt HEVC-Alpha im Encoder"

RUN cd /src/ffmpeg \
    && PKG_CONFIG_PATH=/opt/ffalpha/lib/pkgconfig ./configure \
        --prefix=/opt/ffalpha \
        --disable-doc --disable-debug --disable-network --disable-autodetect \
        --enable-gpl --enable-libx265 --enable-libvpx --enable-libx264 \
        --enable-libass --enable-libfreetype --enable-libfontconfig --enable-libfribidi \
        --extra-cflags="-DX265_ENABLE_ALPHA" \
        --extra-ldflags="-L/opt/ffalpha/lib -Wl,-rpath,/opt/ffalpha/lib" \
    && make -j"$(nproc)" \
    && make install \
    && strip /opt/ffalpha/bin/ffmpeg /opt/ffalpha/bin/ffprobe

# ------------------------------------------------- 3) Pruefung IM BAU
# Ein Image ohne funktionierenden Alpha-Pfad ist wertlos. Geprueft wird der
# ganze Weg: Formatliste, kodieren, wieder einlesen, Transparenz nachweisen.
# NICHT auf `pix_fmt == yuva420p` pruefen: ffprobe meldet die Spur als
# yuv420p, weil der Kanal als eigene Ebene vorliegt (gemessen). Beweis ist
# der extrahierte Alphakanal: teils transparent UND teils deckend.
# Bewusst mit dem ass-Filter (der Weg des Dienstes) — drawtext ist in diesem
# Bau nicht enthalten, eine Pruefung damit wuerde faelschlich scheitern.
RUN set -e; \
    ffm=/opt/ffalpha/bin/ffmpeg; \
    fp=/opt/ffalpha/bin/ffprobe; \
    $ffm -hide_banner -h encoder=libx265 | grep -q "yuva420p" \
      || { echo "FEHLT: libx265 ohne Alpha (yuva420p)"; exit 1; }; \
    for enc in libx264 libvpx-vp9 prores_ks png; do \
      $ffm -hide_banner -encoders | grep -q " $enc " || { echo "FEHLT: Encoder $enc"; exit 1; }; \
    done; \
    $ffm -hide_banner -filters | grep -qE '\bass\b +V->V' || { echo "FEHLT: ass-Filter"; exit 1; }; \
    mkdir -p /tmp/pruef; \
    printf '%s\n' \
      '[Script Info]' 'ScriptType: v4.00+' 'PlayResX: 320' 'PlayResY: 180' '' \
      '[V4+ Styles]' \
      'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding' \
      'Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,5,10,10,10,1' '' \
      '[Events]' \
      'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text' \
      'Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hallo' \
      > /tmp/pruef/t.ass; \
    $ffm -hide_banner -loglevel error -y -f lavfi \
      -i "color=c=black@0.0:s=320x180:r=10:d=1,format=yuva420p" \
      -vf "ass=/tmp/pruef/t.ass:alpha=1" \
      -c:v libx265 -pix_fmt yuva420p -tag:v hvc1 -movflags +faststart /tmp/pruef/alpha.mp4; \
    $ffm -hide_banner -loglevel error -y -i /tmp/pruef/alpha.mp4 -frames:v 1 \
      -vf alphaextract -f rawvideo -pix_fmt gray /tmp/pruef/a.raw; \
    $ffm -hide_banner -loglevel error -y -i /tmp/pruef/alpha.mp4 -frames:v 1 \
      -f rawvideo -pix_fmt gray /tmp/pruef/bild.raw; \
    test -s /tmp/pruef/a.raw || { echo "FEHLT: Alpha nicht zuruecklesbar"; exit 1; }; \
    deckend=$(tr -d '\000' < /tmp/pruef/a.raw | wc -c); \
    gesamt=$(wc -c < /tmp/pruef/a.raw); \
    text=$(python3 -c "d=open('/tmp/pruef/bild.raw','rb').read(); print(sum(1 for b in d if b>200))"); \
    echo "Alpha-Pruefung: $deckend von $gesamt Bytes deckend, $text helle Bildpunkte (Text)"; \
    test "$deckend" -lt "$gesamt" || { echo "FEHLT: keine Transparenz im Ergebnis"; exit 1; }; \
    test "$deckend" -gt 0 || { echo "FEHLT: kein deckender Text"; exit 1; }; \
    test "$text" -gt 0 || { echo "FEHLT: kein Text im Bild"; exit 1; }; \
    rm -rf /tmp/pruef; \
    echo "ffmpeg mit HEVC-Alpha OK"

FROM python:3.12-slim
COPY --from=build /opt/ffalpha /opt/ffalpha
# Laufzeit-Bibliotheken fuer die mitgebauten Binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
      libass9 libfreetype6 libfontconfig1 libfribidi0 libharfbuzz0b \
      libvpx9 libx264-164 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && /opt/ffalpha/bin/ffmpeg -hide_banner -h encoder=libx265 | grep -q yuva420p \
    && echo "ffalpha-Image bereit (HEVC-Alpha vorhanden)"
