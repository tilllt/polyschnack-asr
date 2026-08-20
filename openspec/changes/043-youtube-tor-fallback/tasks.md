# Tasks — Change 043: YouTube-Import Tor-Fallback

## Task 1: Entscheidungen (User)

- [ ] Tor-Fallback standardmäßig an oder aus (Empfehlung: aus)
- [ ] ps-tor immer im Stack oder on-demand
- [ ] Tor-Downloads nur eingeloggt?

## Task 2: ps-tor-Container

- [ ] Dockerfile (alpine + tor + libevent, SOCKS5 9050)
- [ ] Healthcheck (Bootstrap/TCP-Check)
- [ ] compose.yml-Eintrag + Env-Variablen
- [ ] `.env.example` ergänzen

## Task 3: url_import.py — Fallback-Stufe

- [ ] Bot-Signatur-Erkennung („Sign in to confirm", 403, nsig-Fehler)
- [ ] SOCKS5-Proxy-Download via yt-dlp `--proxy`
- [ ] Circuit-Rotation (SIGHUP an ps-tor) mit max. Versuchen
- [ ] Nur-Audio-Format + Größen-Limit
- [ ] Sequenzielle Queue (max. 1 Tor-Download gleichzeitig)

## Task 4: UI

- [ ] Status „Download über anonymes Netzwerk" (echter Fortschritt)
- [ ] Fehlertext nach allen Circuits (mit yt-dlp-Desktop-Hinweis)

## Task 5: Tests

- [ ] Unit: Bot-Erkennung, Circuit-Logik, Größen-Limit, Proxy-Arg
- [ ] Compose-Smoke: ps-tor gesund, Webapp erreicht 9050
- [ ] Alle bestehenden URL-Import-Tests weiter grün

## Task 6: Commit + Deploy

- [ ] Commit + Push
- [ ] CI grün prüfen und melden
- [ ] Deploy auf Box (mit Change 040/041/042/044)
