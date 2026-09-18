# Change 200 — Tasks

## Phase 1: Render-Dienst (`render-service/`)

- [x] `app.py`: FastAPI mit `/health`, `/render`, `/jobs/{id}`, `/jobs/{id}/file`,
      `/jobs/{id}` (DELETE); Job-Queue mit 1 Slot; ehrlicher Fortschritt aus
      `ffmpeg -progress`
- [x] Formate: `burn_mp4`, `alpha_webm`, `alpha_mov` (+ `alpha_png` optional)
- [x] Encoder-Erkennung beim Start (`ffmpeg -encoders`), `/health` meldet nur
      tatsächlich vorhandene Formate
- [x] `Dockerfile`: ffmpeg + libass + fonts-liberation + fontconfig-Alias
      Arial → Liberation Sans; Healthcheck
- [x] Aufräumen: TTL 24 h, DELETE, Startaufräumen alter Jobs
- [x] Tests: Argumentbau der Formate, Alpha-Prüfung pixelweise, TTL, Queue

## Phase 2: Anbindung in der Webapp

- [x] `export/render_client.py`: Health-Probe (gecacht), Job-Start (ASS + optional
      Video), Statusabfrage, Datei streamen
- [x] `render_available` aus der Health-Probe statt hart `False`;
      `GET /api/export/presets` liefert die Formate mit
- [x] `POST /api/recordings/{id}/export` startet einen Render-Job (202) statt 503
- [x] `GET /api/recordings/{id}/export/jobs/{job_id}` (Status) und
      `.../file` (Download) — Zugriff wie beim ASS-Export (read), bei Share-Links
      nur mit `read`
- [x] Tests: Dienst fehlt → 503 wie bisher; Dienst antwortet → Job wird gestartet,
      Fehler des Dienstes werden als Klartext gemeldet

## Phase 3: GUI

- [x] Export-Dialog: Format-Auswahl (nur vorhandene Formate), Auflösung/FPS,
      Hintergrundfarbe für `burn_mp4`
- [x] Echter Fortschrittsbalken (Prozent aus dem Dienst), Abbrechen, Download
      über die API-URL (kein Blob — Lehre aus Change 193)
- [x] Keine funktionslosen Knöpfe: ohne Dienst bleibt der Hinweis
- [x] i18n de/en/pt; Tests mit gemockter API

## Phase 4: Betrieb

- [x] Compose-Service `ps-render` (Profil `render`) in `compose.yml` +
      `RENDER_URL` in der Webapp
- [x] CI-Job `build-render` (Muster der anderen Dienste) + `needs:` im Mirror-Job
- [ ] Deploy auf die KI-Box, `render_available: true` live prüfen
- [ ] Admin-Doku: „Video-Export (optionaler Render-Dienst)"
- [ ] Abnahme: alle Formate auf Prod einmal rendern, Datei mit ffprobe prüfen
      (Alpha-Kanal vorhanden), Download im Browser

## Abnahme (Zwischenstand 17.09.2026)

Umgesetzt und geprüft, aber noch **nicht** auf Prod ausgerollt:

- Dienst: 9 Tests grün, pixelweise Alpha-Nachweis (WebM 96 % transparent mit
  weißer Schrift, ProRes 4444 mit Alpha, MP4 mit sichtbaren Untertiteln).
- Webapp: 8 neue API-Tests (21 in `tests/test_export_ass_api.py` grün) —
  Dienst fehlt → 503 mit Hinweis; Format startet Job; Status wird durchgereicht;
  Datei wird gestreamt; Format ohne Encoder → 400.
- GUI: 2 neue Dialog-Tests (14 grün, ganze Suite 463) — Video-Auswahl nur mit
  Dienst, Start → Poll → Download-Link auf die API-URL (kein Blob).

Offen: Deploy auf die KI-Box (Profil `render`), Live-Probe mit allen Formaten auf
einem echten Recording, Admin-Doku, Abnahme.

## Fehlerbehebung 18.09.2026 (gemeldet: "Download bricht ab, bevor das Video da ist")

Belege: `docker inspect` (Container-StartedAt 09:18:40Z lag zwischen den beiden
Aufträgen des Nutzers), Render-Log, Webapp-Traceback
(`httpx.ResponseNotRead` in `render_client.open_file`), öffentlicher Abruf
(21 Byte Fehlertext statt 330.097 Byte Datei).

- [x] Dienst: Auftragszustand als `job.json` sichern, beim Start rekonstruieren
      (auch aus älteren Verzeichnissen mit nur `meta.json`)
- [x] Dienst: Vollständigkeitsprüfung (ffprobe-Dauer vs. erwartete Dauer; leere
      oder unlesbare Datei; kaputtes ZIP) — Unvollständiges wird **nie** als
      fertig ausgeliefert, sondern als gescheitert geführt
- [x] Dienst: Wiederherstellung im Log melden (live: "recovery: 6 Aufträge …")
- [x] Webapp: Streaming-Fehlerantwort erst lesen, dann auswerten → 404 mit
      Klartext statt 500
- [x] Webapp: `Content-Length` durchreichen (abgeschnittener Transfer wird als
      Fehler sichtbar statt still eine halbe Datei zu speichern)
- [x] Tests: 13 Render-Tests (Neustart, unvollständige Datei, vollständige
      Alt-Datei), 23 Webapp-Export-Tests (Streaming-Fehlerantwort, 404 statt 500,
      Größen-Header)

**Abnahme über die öffentliche URL (Revision 7ade63c1):**
Download HTTP 200 mit `content-length: 330097`, Datei vollständig (webm,
30,88 s); unbekannter Auftrag → HTTP 404 mit `unknown_job` statt 500; Presets
melden weiterhin `render_available: true` mit vier Formaten; ASS-Download
unverändert (200, 40 Dialogue-Zeilen).

Offen (Härtung, nicht Teil der Meldung): Auftrag ↔ Aufnahme fest verknüpfen,
damit ein Auftrag nicht über eine beliebige eigene Aufnahme-ID abrufbar ist.

## Handy-Schnitt und HEVC mit Alpha (Nachtrag)

Ausgelöst durch die Meldung „keines der Exportformate lässt sich in KineMaster
importieren". Der erste geprüfte Verdacht war ein echter Fehler, der zweite ein
fehlendes Format.

### Gefundener Fehler: MP4 ohne Bildspur

- [x] `burn_mp4` bei einer reinen Tonaufnahme: es wurde nur die Tondatei als
      Eingabe übergeben, darauf ein Videofilter und `-c:v libx264`. ffmpeg lief
      fehlerfrei durch und schrieb eine MP4 **ohne Videospur** (662 KB reiner
      Ton). Bildquelle wird jetzt erzeugt (lavfi `color`), die Tondatei als
      zweite Eingabe geführt; `ffprobe` entscheidet, ob eine Datei Bild oder nur
      Ton enthält.
- [x] Regressionstest: Videospur (h264), `pix_fmt`, Tonspur (aac) und sichtbare
      Untertitel an echten Untertitelzeiten.

### Neue Formate für den Handy-Schnitt

- [x] `screen_mp4` — schwarzer Grund, im Schnittprogramm als Ebene mit
      Mischmodus „Screen" (KineMaster hat 24 Modi); der Grund verschwindet.
      Hintergrund ist fest schwarz, unabhängig vom Parameter.
- [x] `chroma_mp4` — grüner Grund für Chroma Key, Farbe einstellbar.
- [x] Formatbeschreibungen nennen, welches Programm sie liest (inklusive des
      Hinweises, dass KineMaster WebM und ProRes nicht importiert).

### HEVC mit Alpha (`hevc_alpha`)

Drei Dinge müssen zusammenkommen, jedes einzeln gemessen:

- [x] x265 mit `-DENABLE_ALPHA=ON` bauen. Debian baut ohne: die Option `alpha`
      ist über `x265_param_parse` nicht einmal registriert (Nachweis per ctypes,
      Kontrollwerte `log-level`/`crf` greifen; Debian lehnt `alpha` ab, eigener
      Bau nimmt es an).
- [x] Geteilte x265-Bibliothek ins Prefix kopieren und `x265.pc` selbst
      schreiben: `cmake --install` legt nur die statische Bibliothek, die Header
      und das CLI ab — keine `.so`, keine pkg-config-Datei. Ohne beides meldet
      ffmpegs Linktest „x265 not found".
- [x] ffmpeg aus Quellen mit Alpha-Code und `-DX265_ENABLE_ALPHA` bauen.
      Version 7.1 enthält den Code nicht, ab 8.0 ist er drin; ffmpegs `configure`
      setzt den Schalter nirgends.
- [x] Eigenes Image `ffalpha-build/` (Tag `:v1`, ~10 Min Bau) mit Prüfung **im
      Bau**: Formatliste zeigt `yuva420p`, Rundlauf kodieren → `alphaextract`
      liefert teils transparent UND teils deckend. Ohne Nachweis bricht der Bau
      ab. Der Render-Container kopiert `/opt/ffalpha` und nutzt es über
      `RENDER_FFMPEG`/`RENDER_FFPROBE`.
- [x] Neues Format `hevc_alpha`, nur angeboten, wenn die Fähigkeit wirklich da
      ist; `/health` meldet `x265_alpha`.
- [x] Der Bau fing zwei Fehler, die sonst in den Betrieb gelangt wären:
      fehlender PNG-Encoder (`--disable-autodetect` schaltet zlib ab) und eine
      Prüfung im Render-Image, die gegen das Debian-ffmpeg statt gegen das
      mitgebaute lief.
- [x] Achtung beim Nachmessen: `ffprobe` meldet die Spur als `yuv420p`, der
      Kanal liegt als eigene Ebene vor. Belastbar ist nur der extrahierte
      Alphakanal.

**Abnahme über die öffentliche URL (Revision e9713cb1):** `/health` meldet
`x265_alpha: true` und sieben Formate; Auftrag `ecd65d36b8224ace` fertig
(183.250 Byte, HEVC 1280×720, 24,4 s); im Container gemessen an vier echten
Untertitelzeiten: 99,4–99,7 % transparent, 0,23–0,48 % deckend, 303–720 helle
Textpunkte.

**Offen (nicht durch uns prüfbar):** ob KineMaster die Datei tatsächlich mit
Transparenz importiert. Der Import ist auf dem Gerät zu testen; unsere Prüfung
endet beim Nachweis des Alphakanals.
