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
