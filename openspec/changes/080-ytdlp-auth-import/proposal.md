# Change 080: Sichere yt-dlp-Zusatzparameter für den URL-Import (Anmeldedaten & Cookies)

## Problem

Der URL-Import (`POST /api/recordings/from-url`) lädt nur öffentliche
Medien: yt-dlp wird mit einer festen Argumentliste aufgerufen (kein Weg
für Login-Pflicht-Inhalte). Wer z. B. ein privates Vimeo-Video oder eine
geschützte PeerTube-Instanz transkribieren will, kann das nicht über die
GUI — der bisherige Hinweis („yt-dlp auf dem Desktop nutzen") ist ein
Workaround, kein Feature.

Die GUI darf dabei NICHT einfach freie yt-dlp-Argumente durchreichen:
ein Client-Argument wie `--exec` wäre Remote-Code-Execution, `--config-location`
beliebige Datei-Lesevorgänge, `--proxy` ein SSRF-Kanal. Zusätzlich darf
ein Passwort nirgends landen: nicht in `ps`/argv, nicht in Logs, nicht in
Fehlermeldungen, nicht dauerhaft auf der Platte.

## Ziel

Der URL-Import-Dialog bekommt einen optionalen Bereich „Anmeldedaten" —
Benutzername, Passwort (sowie optional eine Cookies-Datei als Upload).
Verhaltens-Delta:

1. **API:** `POST /api/recordings/from-url` akzeptiert optional
   `username`, `password`, `video_password` (Form) und `cookies`
   (Datei-Upload).
   → Ein API-Client/User kann jetzt private/geschützte Medien importieren,
   die vorher mit „yt-dlp failed" scheiterten. Konkretes Beispiel:
   Vimeo-Video mit Passwort-Schutz (`--video-password`) und/oder
   Account-Login (`--username`/`--password`).
2. **Sicherheit (Whitelist):** Es werden NUR die freigegebenen Optionen
   an yt-dlp gereicht (`--no-config-locations --config-locations <transiente
   Datei>` mit `username=`/`password=`, optional `--cookies <Datei>`).
   Keine anderen Client-gesteuerten Argumente erreichen die Kommandozeile.
   Die bestehende `--`-URL-Absicherung und der SSRF-Guard bleiben unverändert.
3. **Kein Passwort in argv/Logs/Fehlern:** Credentials laufen über eine
   transiente 0600-Config-Datei im Tempdir (wird nach dem Request gelöscht),
   Werte werden per `shlex.quote` kodiert (Sonderzeichen wie `#`/Leerzeichen
   funktionieren). Vor dem Loggen/Weiterreichen von yt-dlp-Stderr werden
   Passwort und Benutzername durch `***` ersetzt.
4. **Retry-Kaskade trägt die Anmeldedaten mit:** zweiter Versuch,
   Player-Client-Retries und Tor-Fallback verwenden dieselben Parameter.
   Ausnahme: Ist Auth (Credentials ODER Cookies) gesetzt, wird der
   Tor-Fallback ÜBERSPRUNGEN (Login/Cookies über Tor-Exit-IPs = Account-Risiko).
5. **Validierung:** `username` und `password` nur zusammen, jeweils max.
   256 Zeichen, keine Steuerzeichen (Newline etc.). Cookies-Datei max.
   1 MiB. Verstöße → 422 mit klarer Meldung.
6. **GUI:** Der URL-Tab bekommt einen aufklappbaren Bereich
   „Anmeldedaten (optional)" mit Benutzername/Passwort-Feldern und
   Cookies-Datei-Picker; Werte werden nicht persistiert (nur
   Komponenten-State, nach Import geleert). i18n de/en/pt.

## Specs-Delta

- `MODIFIED` Capability `url-import` (siehe `specs/`-Ordner im Change,
  sofern vorhanden): Endpoint-Delta + Sicherheits-Anforderungen.

## Downgrade

Entfernen der Form-Felder und der Config-/Cookies-Argumente aus
`url_import.py` + GUI-Bereich; yt-dlp-Aufrufe zurück auf die feste
Liste. Kein Datenmodell, keine Migration, keine Image-Änderung
(yt-dlp ist im Image bereits vorhanden).
