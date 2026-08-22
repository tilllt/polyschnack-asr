# Design — Change 080: Sichere yt-dlp-Zusatzparameter

## Entscheidungen

### D1: Whitelist statt freier Argumente (Kernprinzip)
Die GUI sendet nur **Key/Value-Felder** (`username`, `password`,
`cookies`-Datei). Das Backend baut daraus eine **feste** yt-dlp-Argumentliste.
Freie Client-Argumente sind ausgeschlossen, weil yt-dlp-Optionen
gefährliche Seiteneffekte haben: `--exec` (RCE), `--config-location`
(arbitrary file read), `--proxy` (SSRF), `--cookies` (Datei-Lesen).
Das bestehende Muster (feste Liste + `--` vor der URL) wird exakt
fortgeführt — die URL bleibt die einzige „freie" Eingabe.

### D2: Transiente Config-Datei statt argv (kein Passwort in `ps`)
`--username/--password` direkt in argv wären in der Prozessliste sichtbar
(im Container zwar nur für denselben User, aber vermeidbar). Stattdessen:
- yt-dlp liest Config-Dateien mit `shlex.split(comments=True)` und parst
  sie mit optparse (verifiziert in `yt_dlp/utils/_utils.py`
  `Config.read_file` + `options.py` `parse_known_args`). Optionen brauchen
  den `--`-Präfix (`--username=`), sonst werden sie als Positional-Argumente
  (URLs) behandelt — per Real-Binary-Test belegt.
- Wir schreiben in das bestehende `TemporaryDirectory` eine Datei
  `ytdlp-auth.conf` (0600) mit `--username=<wert>`/`--password=<wert>`
  und optional `--video-password=<wert>` (Vimeo-Stil: Passwort pro Video,
  unabhängig vom Account-Login; wird von 10+ Extractoren unterstützt:
  Vimeo, PeerTube, Dropbox, Loom, Wistia, Youku …), Werte mit
  `shlex.quote()` kodiert → beliebige Sonderzeichen
  (`#`, Leerzeichen, Quotes) sind sicher.
- Aufruf mit `--no-config-locations --config-locations <datei>`:
  damit wird NUR unsere Datei geladen (System-/User-Config im Container
  ignoriert; deterministisch, nur Whitelist-Keys).
- `TemporaryDirectory` löscht die Datei nach dem Request (bei Erfolg
  wie bei Fehlern). Kein DB-Feld, kein Persistieren.

Warum nicht `.netrc`: netrc bindet Credentials an `machine <name>`
(z. B. `youtube`, `vimeo`, `generic`) — der Extractor ist erst zur
Laufzeit bekannt, ein falscher Machine-Name würde still scheitern.
Die Config-Datei mit `username=`/`password=` gilt für JEDEN Extractor.

### D3: Cookies-Upload als Datei
`cookies` (UploadFile) wird auf ≤ 1 MiB begrenzt gelesen und als
`cookies.txt` (0600) ins Tempdir geschrieben, Aufruf mit `--cookies <pfad>`.
Kein Validieren des Formats (Netscape-Cookie-Format, yt-dlp akzeptiert
auch Abweichungen) — die Datei ist Eigentum des Users; nur die Größe
wird begrenzt (Memory-Schutz).

### D4: Log-/Fehler-Sanitizing
`_redact(text, *secrets)` ersetzt alle Vorkommen von Passwort und
Benutzername durch `***` — angewendet auf yt-dlp-Stderr VOR
`log.warning` und VOR der HTTPException-`detail`. yt-dlp selbst
verschleiert `--password`-Werte in seinem Debug-Output
(`hide_login_info` in options.py), aber Defense in Depth.

### D5: Retry-Kaskade + Tor-Skip
- `_run_ytdlp`, `_run_ytdlp_client` und `_run_ytdlp_proxy` bekommen
  optionale Auth-Argumente (config_path, cookies_path) und hängen sie
  an die feste Basis-Liste.
- **Tor-Fallback:** Wenn Auth (username/password ODER cookies) gesetzt
  ist, wird der Tor-Pfad übersprungen (`log.info`, kein Rate-Limit-Slot
  verbraucht). Begründung: Login/Cookies über Tor-Exit-IPs = Account-Risiko
  (fremde Exit-IP sieht die Session); Tor ist außerdem für Bot-Block
  gedacht, nicht für Auth-Inhalte.

### D6: Validierung
- `username` XOR `password` (nur eines gesetzt) → 422
  („username and password must be provided together").
- `video_password` ist UNABHÄNGIG (darf allein stehen) — gleiche
  Längen-/Steuerzeichen-Regeln.
- Länge > 256 Zeichen → 422.
- Steuerzeichen (`ord(c) < 32`) in username/password → 422
  (schützt die Config-Datei zusätzlich zur shlex-Quote-Kodierung).
- Cookies-Datei: `len(data) > 1 MiB` → 422; leere Datei → 422.
- Kein Anon-Gate: Auch anonyme Sessions dürfen Auth-Downloads nutzen —
  die Credentials sind User-Eigentum für den eigenen Download, es wird
  nichts serverseitig gespeichert oder weitergegeben.

## Offene Fragen
- Keine (Entscheidungen D1–D6 sind fix; Umsetzung folgt tasks.md).
