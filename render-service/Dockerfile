# ==============================================================
# PolySchnack Render-Dienst (Change 200)
# ==============================================================
# Brennt .ass-Untertitel in ein Video ein oder erzeugt ein Untertitel-Video
# MIT Alphakanal (transparenter Hintergrund) fuer Schnittprogramme.
#
# Kein GPU-Zwang: VP9-Alpha und ProRes 4444 haben keinen nutzbaren
# Hardware-Pfad, x264 ist auf CPU ausreichend schnell. Der Container ist
# deshalb schlank (python:slim + ffmpeg) und braucht kein NVIDIA-Toolkit.
#
# Schriften: Die Presets nennen "Arial". Arial ist nicht redistributierbar —
# fonts-liberation liefert die metrik-kompatible Liberation Sans, und die
# fontconfig-Regel unten bildet Arial darauf ab. Der Dienst meldet in
# /health, welche Familie fontconfig tatsaechlich nimmt (Transparenz statt
# stiller Ersatz).
#
# Port 8090 (nicht 8080 — belegt).
# ==============================================================
FROM python:3.12-slim

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-liberation \
      fontconfig \
      curl \
      zip \
    && rm -rf /var/lib/apt/lists/*

# Arial → Liberation Sans (metrik-kompatibel) fuer libass/fontconfig
RUN printf '%s\n' \
      '<?xml version="1.0"?>' \
      '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">' \
      '<fontconfig>' \
      '  <match target="pattern">' \
      '    <test name="family"><string>Arial</string></test>' \
      '    <edit name="family" mode="assign" binding="strong"><string>Liberation Sans</string></edit>' \
      '  </match>' \
      '  <match target="pattern">' \
      '    <test name="family"><string>Helvetica</string></test>' \
      '    <edit name="family" mode="assign" binding="strong"><string>Liberation Sans</string></edit>' \
      '  </match>' \
      '</fontconfig>' \
      > /etc/fonts/conf.d/99-arial-liberation.conf \
    && fc-cache -f >/dev/null

# ffmpeg mit HEVC-Alpha aus dem eigenen Image (ffalpha-build/). Der Bau dauert
# 15-20 Minuten und liegt deshalb nicht hier, sondern in einem selten gebauten
# Image mit fester Version (:v1). Version dort erhoehen = neu bauen.
# Faehigkeit im Betrieb pruefbar: /health meldet x265_alpha.
COPY --from=harbor.rand0m.me/public/polyschnack-asr-ffalpha:v1 /opt/ffalpha /opt/ffalpha
ENV RENDER_FFMPEG=/opt/ffalpha/bin/ffmpeg \
    RENDER_FFPROBE=/opt/ffalpha/bin/ffprobe

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Verify IM BUILD: fehlt libass oder ein Encoder, soll der Build scheitern —
# nicht erst der Nutzer beim Rendern (Lehre aus dem crispasr-Image, das gruen
# baute und auf der Box crashte).
# Geprueft wird das ffmpeg, das der Dienst WIRKLICH benutzt (RENDER_FFMPEG) —
# das Debian-ffmpeg im Image kann kein HEVC-Alpha und taugt nicht als Nachweis.
RUN set -e; \
    ffm="${RENDER_FFMPEG}"; fp="${RENDER_FFPROBE}"; \
    test -x "$ffm" || { echo "FEHLT: RENDER_FFMPEG nicht ausfuehrbar ($ffm)"; exit 1; }; \
    $ffm -hide_banner -filters | grep -qE '\bass\b +V->V' || { echo "FEHLT: libass (ass-Filter)"; exit 1; }; \
    for enc in libx264 libvpx-vp9 prores_ks png libx265; do \
      $ffm -hide_banner -encoders | grep -q " $enc " || { echo "FEHLT: Encoder $enc"; exit 1; }; \
    done; \
    $ffm -hide_banner -h encoder=libx265 | grep -q "yuva420p" \
      || { echo "FEHLT: $ffm ohne HEVC-Alpha (yuva420p)"; exit 1; }; \
    $fp -version >/dev/null || { echo "FEHLT: RENDER_FFPROBE ($fp)"; exit 1; }; \
    fc-match Arial | grep -qi "liberation" || { echo "WARNUNG: Arial bildet nicht auf Liberation ab"; exit 1; }; \
    echo "Render-Image OK: libass + alle Encoder + HEVC-Alpha + Arial-Ersatz vorhanden"

ENV RENDER_DATA=/data/render
RUN mkdir -p /data/render && useradd -m -u 10001 render && chown -R render:render /data/render
USER render

EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
