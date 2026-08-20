# Change 041: YouTube-Import — JS-Runtime (Node.js) + Bot-Schutz-Retry

## Problem

Der YouTube-Import in der Webapp scheitert mit:

1. **`no supported JavaScript runtime was found`** — das Webapp-Docker-Image
   enthält kein Node.js/Deno. Aktuelle yt-dlp-Versionen brauchen ein
   JS-Runtime, um die YouTube-Player-Challenge zu lösen. Ohne Runtime:
   `HTTP Error 403: Forbidden` beim Download (konkret beobachtet bei
   https://www.youtube.com/live/cyWa3CgQvBY am 20.08.2026).
2. **Bot-Schutz-Persistenz** — YouTube blockt Datacenter-IPs mit
   „Sign in to confirm you're not a bot". Der bisherige einfache Retry
   (1× identischer Aufruf) überwindet das nicht; alternative
   Player-Clients (tv/web_embedded/ios) umgehen den Block oft.

## Lösung

- **Dockerfile**: `nodejs` in die apt-Installation aufnehmen (neben
  ffmpeg) → yt-dlp kann die Player-Challenge lösen.
- **url_import.py**: Bei Bot-Schutz-Fehlern (403/„Sign in to confirm"/
  400) zusätzlich mit alternativen Player-Clients retryen
  (`--extractor-args youtube:player_client=tv|web_embedded|ios`).
- **Fehlermeldung**: Eigener, verständlicher Hinweis für das
  JS-Runtime-Problem („Server-Image neu bauen, enthält nodejs") statt
  roher yt-dlp-Ausgabe.

## Tasks

- [ ] Dockerfile: nodejs installieren (apt)
- [ ] url_import.py: _run_ytdlp_client + Bot-Schutz-Retry-Loop
- [ ] _ytdlp_error_hint: JS-Runtime-Hinweis
- [ ] Tests: JS-Runtime-Hint + bestehende URL-Import-Tests grün
