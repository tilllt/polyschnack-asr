# Tasks — Change 080: Sichere yt-dlp-Zusatzparameter (Auth & Cookies)

## Backend (TDD)

### T1 — Validierung (`_validate_auth_input` in url_import.py)
- [ ] Pure Funktion: `(username, password) -> None`, wirft `HTTPException(422)`:
      - nur username ODER nur password gesetzt
      - Länge > 256 Zeichen
      - Steuerzeichen (`ord(c) < 32`) enthalten
- [ ] Tests: 4 Fälle (gültig, nur username, zu lang, Newline)

### T2 — Transiente Auth-Config + Cookies-Datei
- [ ] `_write_auth_files(tmpdir, username, password, cookies_bytes,
      video_password) -> (conf_path | None, cookies_path | None)`:
      - Config-Datei `ytdlp-auth.conf` (0600), Inhalt
        `--username=<shlex.quote(u)>`/`--password=<shlex.quote(p)>` und
        optional `--video-password=<shlex.quote(vp)>` (Vimeo-Stil, kann
        allein stehen)
      - Cookies-Datei `cookies.txt` (0600) mit den Bytes
      - Rückgabe der Pfade (None wenn nicht gesetzt)
- [ ] Tests: Dateien existieren im Tempdir, Perms 0600, shlex.quote bei
      Sonderzeichen (`#`, Leerzeichen, `'`)

### T3 — yt-dlp-Aufrufe erweitern
- [ ] `_run_ytdlp` / `_run_ytdlp_client` / `_run_ytdlp_proxy` bekommen
      optionale `conf_path`/`cookies_path`-Parameter; bei gesetztem
      conf_path: `--no-config-locations --config-locations <pfad>`
      in die Argumentliste (vor `--`); bei cookies_path: `--cookies <pfad>`
- [ ] Test: subprocess-args enthalten die neuen Flags genau dann, wenn
      Auth gesetzt ist; ohne Auth exakt alte Argumentliste

### T4 — Endpoint-Signatur + Retry-Kaskade + Sanitizing
- [ ] Form-Felder `username: Optional[str]`, `password: Optional[str]`,
      `cookies: Optional[UploadFile]` (File) ergänzen
- [ ] Cookies-Datei ≤ 1 MiB lesen (überschreitung → 422), leere → 422
- [ ] `_redact(text, *secrets)` Helper + Anwendung auf stderr vor
      `log.warning` und HTTPException-detail (alle Fehlerpfade)
- [ ] Tor-Fallback: wenn Auth gesetzt → `log.info` + Skip (kein
      Rate-Limit-Slot, kein Docker-Proxy-Aufruf)
- [ ] Retry-Kaskade reicht conf/cookies an alle Versuche weiter
- [ ] Tests: Passwort nicht in Fehler-detail, nicht in caplog; Tor-Skip
      bei Auth (Docker-Proxy nicht aufgerufen); erfolgreicher Import mit
      Auth legt Recording an; Cookies-Upload wird als Datei geschrieben

## Frontend

### T5 — api.ts
- [ ] `importFromUrl(..., username?, password?, cookiesFile?)`: Feld
      `username`/`password` nur bei gesetztem Wert appenden, `cookies`
      als File appenden

### T6 — UploadZone.tsx (UrlTab)
- [ ] Aufklappbarer Bereich „Anmeldedaten (optional)" (Detail/Summary oder
      Toggle): Benutzername (text), Passwort (type=password), Cookies-
      Datei-Picker (input type=file accept=.txt)
- [ ] Werte in Komponenten-State, nach erfolgreichem Import geleert
- [ ] i18n-Keys de/en/pt (Default en)

## Verifikation
- [ ] Backend-Tests: `pytest tests/test_url_import.py` grün
- [ ] Frontend: `npm test`, `npm run build`, `tsc --noEmit`
- [ ] Vollsuite `webapp/run_full_suite.sh` → `GESAMT fail=0`
- [ ] Commit + Push (GitLab main), CI-Check nach Push
