# Change 200 — Tasks

## Phase 1: Render-Dienst (`render-service/`)

- [ ] `app.py`: FastAPI mit `/health`, `/render`, `/jobs/{id}`, `/jobs/{id}/file`,
      `/jobs/{id}` (DELETE); Job-Queue mit 1 Slot; ehrlicher Fortschritt aus
      `ffmpeg -progress`
- [ ] Formate: `burn_mp4`, `alpha_webm`, `alpha_mov` (+ `alpha_png` optional)
- [ ] Encoder-Erkennung beim Start (`ffmpeg -encoders`), `/health` meldet nur
      tatsächlich vorhandene Formate
- [ ] `Dockerfile`: ffmpeg + libass + fonts-liberation + fontconfig-Alias
      Arial → Liberation Sans; Healthcheck
- [ ] Aufräumen: TTL 24 h, DELETE, Startaufräumen alter Jobs
- [ ] Tests: Argumentbau der Formate, Alpha-Prüfung pixelweise, TTL, Queue

## Phase 2: Anbindung in der Webapp

- [ ] `export/render_client.py`: Health-Probe (gecacht), Job-Start (ASS + optional
      Video), Statusabfrage, Datei streamen
- [ ] `render_available` aus der Health-Probe statt hart `False`;
      `GET /api/export/presets` liefert die Formate mit
- [ ] `POST /api/recordings/{id}/export` startet einen Render-Job (202) statt 503
- [ ] `GET /api/recordings/{id}/export/jobs/{job_id}` (Status) und
      `.../file` (Download) — Zugriff wie beim ASS-Export (read), bei Share-Links
      nur mit `read`
- [ ] Tests: Dienst fehlt → 503 wie bisher; Dienst antwortet → Job wird gestartet,
      Fehler des Dienstes werden als Klartext gemeldet

## Phase 3: GUI

- [ ] Export-Dialog: Format-Auswahl (nur vorhandene Formate), Auflösung/FPS,
      Hintergrundfarbe für `burn_mp4`
- [ ] Echter Fortschrittsbalken (Prozent aus dem Dienst), Abbrechen, Download
      über die API-URL (kein Blob — Lehre aus Change 193)
- [ ] Keine funktionslosen Knöpfe: ohne Dienst bleibt der Hinweis
- [ ] i18n de/en/pt; Tests mit gemockter API

## Phase 4: Betrieb

- [ ] Compose-Service `ps-render` (Profil `render`) in `compose.yml` +
      `RENDER_URL` in der Webapp
- [ ] CI-Job `build-render` (Muster der anderen Dienste) + `needs:` im Mirror-Job
- [ ] Deploy auf die KI-Box, `render_available: true` live prüfen
- [ ] Admin-Doku: „Video-Export (optionaler Render-Dienst)"
- [ ] Abnahme: alle Formate auf Prod einmal rendern, Datei mit ffprobe prüfen
      (Alpha-Kanal vorhanden), Download im Browser
