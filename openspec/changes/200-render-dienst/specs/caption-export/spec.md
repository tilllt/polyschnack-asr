# Caption Export (Change 200 — Ergänzungen)

## ADDED Requirements

### Requirement: Video-Rendering über den optionalen Render-Dienst

- **Ablauf:** Läuft der Dienst `ps-render`, kann der Nutzer im Export-Dialog ein
  Video erzeugen lassen; ohne ihn bleibt es beim ASS-Download mit Hinweis.
- **Eingaben:** `POST /api/recordings/{id}/export` mit `mode="render"`,
  `format` (`burn_mp4` | `screen_mp4` | `chroma_mp4` | `hevc_alpha` |
  `alpha_webm` | `alpha_mov` | `alpha_png`), Preset und Parametern.
- **Handy-Schnitt:** KineMaster und Verwandte lesen MP4/MOV/3GP mit H.264/H.265.
  Als einziges Alpha-Format unterstützt KineMaster (ab 7.1) **HEVC mit Alpha in
  MP4** — dafür gibt es `hevc_alpha`. `screen_mp4` (schwarzer Grund, Mischmodus
  „Screen") und `chroma_mp4` (grüner Grund) sind die Wege ohne Alphakanal.
- **Ausgaben:** 202 mit Job-Objekt; Status über den Dienst; fertige Datei über
  `GET /api/recordings/{id}/export/jobs/{job_id}/file`.
- **Ergebnis:** `render_available` wird aus `/health` des Dienstes ermittelt,
  nicht hart gesetzt; fehlt der Dienst, antwortet die API unverändert mit 503
  `render_unavailable` und Hinweis auf den ASS-Download.
- **Architektur:** `export/render_client.py` → `render-service/`, Compose-Profil `render`.

#### Scenario: Render-Dienst vorhanden

- **Akteure:** Besitzer einer Aufnahme mit echten Wortzeiten.
- **Eingaben:** `POST /api/recordings/{id}/export` mit `mode="render"`,
  `format="alpha_webm"`.
- **Ergebnis:** 202 mit `job_id`; anschließend liefert der Status Fortschritt
  0…1 und nach Abschluss die Datei mit `Content-Type: video/webm`
  **mit Alphakanal** (`yuva420p`).

#### Scenario: Render-Dienst fehlt

- **Akteure:** Installation ohne `ps-render`.
- **Eingaben:** `POST /api/recordings/{id}/export` mit `mode="render"`.
- **Ergebnis:** 503 `{"error": "render_unavailable"}` mit Hinweis auf den
  ASS-Download — unverändertes Verhalten aus Change 193.

#### Scenario: Kein Format ohne Encoder

- **Akteure:** Betreiber, dessen Image einen Encoder nicht enthält.
- **Ergebnis:** Der Dienst meldet das Format nicht in `/health`, die GUI bietet
  es nicht an, und die API weist ein nicht unterstütztes Format mit 400
  `unsupported_format` zurück.

#### Scenario: HEVC mit Alpha nur bei nachgewiesener Fähigkeit

- **Akteure:** Betreiber mit Alpha-fähigem ffmpeg im Image.
- **Eingaben:** `format="hevc_alpha"`.
- **Ergebnis:** `/health` meldet `x265_alpha: true` und führt `hevc_alpha` in
  den Formaten; die Datei ist HEVC 1280×720 mit echtem Alphakanal (Stichprobe:
  an Untertitelzeiten teils transparent, teils deckend, sichtbarer Text).
- **Gegenprobe:** Ein ffmpeg ohne `yuva420p` in der Formatliste des Encoders
  führt dazu, dass `hevc_alpha` **gar nicht** angeboten wird (Nachweis im
  Container: `FEHLT: Encoder png` → `alpha_png` wurde nicht gelistet, statt
  beim Rendern zu scheitern).

### Requirement: Ehrlicher Fortschritt beim Rendern

- **Ablauf:** Während eines Render-Jobs fragt die GUI den Status ab.
- **Ergebnis:** Der Fortschritt stammt aus `ffmpeg -progress` (`out_time_us` /
  erwartete Dauer). Solange keine Zeit vorliegt, bleibt er bei 0 und der Zustand
  ist `running` — keine Zeitschätzung, keine erfundenen Prozente.
- **Architektur:** `render-service/app.py` (Job-Queue mit 1 Slot).

#### Scenario: Fortschritt während des Renderns

- **Eingaben:** `GET /api/recordings/{id}/export/jobs/{job_id}` alle 2 s.
- **Ergebnis:** `state="running"` mit monoton steigendem `progress` (0…1);
  `state="done"` erst, wenn die Datei vollständig geschrieben ist.
