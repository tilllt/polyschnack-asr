# Tasks — Change 043: YouTube-Import Tor-Fallback

## Entscheidungen (User, 2026-08-20)

- [x] **Tor-Fallback standardmäßig AUS** — `POLYSCHNACK_TOR_FALLBACK=off`,
      Admin schaltet pro Installation an (Option zum Anschalten)
- [x] **On-demand**: ps-tor-Container existiert (Profil `ps-tor` in
      compose.backends.yml), startet NICHT automatisch — Webapp startet ihn
      per Docker-Proxy beim ersten Tor-Import, stoppt nach Leerlauf
- [x] **Nur eingeloggte User** — anon-Sessions bekommen den Tor-Fallback nicht
- [x] **Rate-Limiting einbauen** (Pflicht, User-Vorgabe)

## Task 1: ps-tor-Container

- [ ] Dockerfile (alpine + tor + libevent, SOCKS5 9050)
- [ ] Healthcheck (Bootstrap/TCP-Check)
- [ ] compose.backends.yml-Eintrag mit `profiles: ["ps-tor"]` (on-demand)
- [ ] `.env.example` ergänzen (POLYSCHNACK_TOR_FALLBACK etc.)

## Task 2: url_import.py — Fallback-Stufe

- [ ] Bot-Signatur-Erkennung („Sign in to confirm", 403, nsig-Fehler)
- [ ] Nur eingeloggt: anon → kein Tor-Fallback (HTTP 403/ohne Fallback)
- [ ] On-demand-Start ps-tor via DockerProxyClient (state → start → health wait)
- [ ] SOCKS5-Proxy-Download via yt-dlp `--proxy`
- [ ] Circuit-Rotation (SIGHUP an ps-tor) mit max. Versuchen (Default 5)
- [ ] Nur-Audio-Format + Größen-Limit (POLYSCHNACK_TOR_MAX_SIZE_MB, Default 500)

## Task 3: Rate-Limiting

- [ ] Tor-Downloads: max. N pro User pro Zeitfenster (Default z.B. 2/h)
- [ ] Sequenzielle Queue (max. 1 Tor-Download gleichzeitig, global)
- [ ] 429 mit verständlicher Meldung + Retry-After

## Task 4: UI

- [ ] Status „Download über anonymes Netzwerk — deutlich langsamer" (echter Fortschritt)
- [ ] Fehlertext nach allen Circuits (mit yt-dlp-Desktop-Hinweis)

## Task 5: Tests

- [ ] Unit: Bot-Erkennung, Circuit-Logik, Größen-Limit, Rate-Limit, anon-Sperre
- [ ] On-demand-Start-Logik (Mock-DockerProxy)
- [ ] Alle bestehenden URL-Import-Tests weiter grün

## Task 6: Commit + Deploy

- [ ] Commit + Push
- [ ] CI grün prüfen und melden
- [ ] Deploy auf Box (mit Change 040/041/042/044/045/046)
