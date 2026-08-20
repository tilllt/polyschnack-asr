# Change 043: ps-tor — Tor-Sidecar für den YouTube-Import-Fallback.
#
# Minimaler Tor-Container (SOCKS5-Proxy). Startet NICHT automatisch:
# compose-Profil "ps-tor" + on-demand-Start durch die Webapp (Docker-Proxy).
# Image ~10 MB, RAM ~30-60 MB — bewusst schlank (kein curl/wget/Python).
FROM alpine:3.20

# tor + libevent (transitive dep) — BusyBox-nc für den Healthcheck.
RUN apk add --no-cache tor \
    && mkdir -p /var/lib/tor \
    && chown -R tor:tor /var/lib/tor

EXPOSE 9050

# SocksPort auf 0.0.0.0:9050 (Container-Netz, nicht Host-geposed).
# Log an stdout für docker logs (collect). ControlPort bewusst AUS
# (Docker-Proxy erlaubt kein SIGHUP/Control — Circuit-Rotation via
# restart, siehe url_import.py).
CMD ["tor", "--SocksPort", "0.0.0.0:9050", "--DataDirectory", "/var/lib/tor", "--Log", "notice stdout"]
