# Change 043: YouTube-Import — Tor-Stealth-Fallback bei Bot-Erkennung

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Feature (Erweiterung Change 041)

## Motivation

Der direkte YouTube-Download scheitert zunehmend an Bot-Erkennung
(„Sign in to confirm you're not a bot", 403, `nsig extraction failed`).
Change 041 ergänzte Player-Client-Retry (tv/web_embedded/ios) + nodejs im
Image. Verifiziert am 2026-08-20: Auch nach Client-Retry blockt YouTube
Datacenter-IPs komplett — erst der Download über einen Tor-Exit (Consumer-IP)
lief durch (229 MiB in 8:19 min, Exit-IP 2 nach Circuit-Wechsel; Exit-IP 1
war geblockt).

Ziel: Als **letzte Stufe** der Download-Kaskade einen Tor-SOCKS5-Fallback
mit Circuit-Rotation einbauen, damit PolySchnack-Nutzer öffentliche
YouTube-Audios auch bei Bot-Erkennung importieren können.

## Stufenkaskade (url_import.py)

1. **Direkt** (bestehend, Change 041): yt-dlp mit Player-Client-Retry
   (tv → web_embedded → ios)
2. **NEU — Tor-Fallback**: nur wenn Stufe 1 mit Bot-Signatur fehlschlägt
   („Sign in to confirm", 403, 400 mit bot-Hinweis, `nsig extraction failed`):
   - yt-dlp über SOCKS5-Proxy (`--proxy socks5://ps-tor:9050`)
   - Circuit-Rotation: bei Fehler SIGHUP an Tor (neue Exit-IP), max
     `POLYSCHNACK_TOR_MAX_CIRCUITS` (Default 5) Versuche
   - nur Audio-Format (m4a/webm/opus), keine Video-Downloads
   - Fehlschlag aller Circuits → ehrlicher Fehler mit Hinweis

## Container `ps-tor` (Sidecar)

- Basis: `alpine:3.20` + `tor` + `libevent` (~30–60 MB RAM, ~10 MB Image)
- SOCKS5 auf `0.0.0.0:9050`, DataDirectory `/var/lib/tor`
- Healthcheck: `tor --verify-config` bzw. Bootstrap-Status-Log
  (oder einfacher: TCP-Check auf 9050 + `curl --socks5` auf eine Test-URL)
- Logs nach stdout (Docker-Collect)

## Konfiguration (compose.yml + Env)

| Variable | Default | Bedeutung |
|---|---|---|
| `POLYSCHNACK_TOR_FALLBACK` | `off` | Schaltet den Fallback an/aus (Admin-Entscheid pro Installation) |
| `POLYSCHNACK_TOR_MAX_CIRCUITS` | `5` | Max. Circuit-Wechsel vor Abbruch |
| `POLYSCHNACK_TOR_MAX_SIZE_MB` | `500` | Max. Dateigröße für Tor-Download (Missbrauchs-Schutz) |
| `TOR_SOCKS5_URL` | `socks5://ps-tor:9050` | Proxy-URL |

Tor-Downloads laufen sequenziell über eine Queue (max. 1 gleichzeitig),
Rate-Limit pro User.

## UI

- Während Tor-Download: Status „Download über anonymes Netzwerk — deutlich
  langsamer" (echter Fortschritt, kein Fake)
- Fehler nach allen Circuits: verständlicher Text + Hinweis auf Desktop-
  yt-dlp-Weg (`uv tool upgrade yt-dlp`)

## Grenzen & bewusste Entscheidungen

- **Tor-Netiquette**: Exit-Nodes sind freiwillig betrieben. Große Downloads
  sind grenzwertig → max. 500 MB, nur Audio, max. 1 parallel, Tor-Fallback
  standardmäßig AUS. Missbrauch würde Exit-IPs auf Blacklists bringen.
- Tor-Exits sind unzuverlässig (YouTube blockt viele) → Fallback ist letzte
  Stufe, kein primärer Weg.
- Rechtslage: Umgehung von Bot-Schutz nur für legitime Nutzung (eigene
  Videos / öffentliche Livestreams). Default off + Admin-Flag dokumentiert
  die bewusste Entscheidung.
- `nsig extraction failed` (zu alte yt-dlp) bleibt eigenständig behoben
  (yt-dlp-Update); der Tor-Fallback hilft dort nicht.

## Offene Fragen

1. Soll der ps-tor-Container immer mitstarten (Default) oder nur on-demand
   beim ersten Tor-Import? → Empfehlung: immer im Stack, ~30 MB RAM sind
   vernachlässigbar, vermeidet Start-Latenz.
2. Dürfen Tor-Downloads auch von anonymen (nicht eingeloggten) Nutzern
   kommen? → Empfehlung: nein, nur eingeloggt (Rate-Limit-Basis).

## Tests

- Unit (url_import): Bot-Signatur-Erkennung, Circuit-Wechsel-Logik,
  Größen-Limit, Proxy-Argument wird korrekt an yt-dlp durchgereicht
- Integration: Mock-SOCKS5-Proxy (lokaler Mini-Tor-Ersatz) — oder echte
  Tor-Instanz im CI-Smoke-Test (langsam, markiert)
- Compose: ps-tor startet, Healthcheck grün, Webapp erreicht 9050

## Checkliste

- [ ] proposal.md angelegt
- [ ] tasks.md angelegt
- [ ] Entscheidung offene Fragen (Default on/off, anon) — User
- [ ] Implementierung
- [ ] Tests
- [ ] Commit + Push
- [ ] Deploy auf Box (mit 040/041/042/044)
