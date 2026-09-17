# Change 200 — Design

## Architektur

```
Webapp (ps-webapp)
  └─ export/render_client.py
       ├─ GET  {RENDER_URL}/health          → Capabilities + Auslastung
       ├─ POST {RENDER_URL}/render          → Job anlegen (ASS + optional Video)
       ├─ GET  {RENDER_URL}/jobs/{id}       → Zustand + ECHTER Fortschritt
       └─ GET  {RENDER_URL}/jobs/{id}/file  → fertige Datei (streamt durch)
ps-render (Compose-Profil "render")
  ├─ ffmpeg 7.x + libass + fontconfig (fonts-liberation als Arial-Ersatz)
  ├─ Job-Queue: 1 Job gleichzeitig (CPU-intensiv, wie Transkription)
  └─ /data/render/<job_id>/ (TTL 24 h, Aufräumen im Dienst)
```

Der Dienst hat **keine Datenbank** und keinen Zugriff auf Aufnahmen: er bekommt
die `.ass`-Datei und optional eine Videodatei und gibt eine Datei zurück. Damit
ist er wegwerfbar und braucht kein Volume außer seinem Arbeitsverzeichnis.

## Formate (Capability-getrieben)

| id | Codec/Container | Alpha | Einsatz |
|---|---|---|---|
| `burn_mp4` | H.264 + AAC, MP4 | nein | fertiges Video, Untertitel eingebrannt |
| `alpha_webm` | VP9 `yuva420p`, WebM | **ja** | Overlay, kleine Datei, im Browser prüfbar |
| `alpha_mov` | ProRes 4444 `yuva444p10le`, MOV | **ja** | Schnittprogramm (Resolve/Premiere) |
| `alpha_png` | PNG-Sequenz, ZIP | **ja** | universell, sehr groß (später) |

`GET /health` meldet nur Formate, deren Encoder im Image vorhanden sind
(`ffmpeg -encoders` einmal beim Start prüfen) — die GUI zeigt genau diese.
So kann niemand ein Format wählen, das die Installation nicht kann.

## Fortschritt (ehrlich)

ffmpeg wird mit `-progress pipe:1 -nostats` gestartet; der Dienst liest
`out_time_us` und teilt durch die erwartete Dauer. Keine Zeitschätzung, keine
Pseudo-Prozente: solange ffmpeg keine Zeit liefert, bleibt der Fortschritt bei 0
und der Zustand ist `running`. Die Webapp pollt `GET /jobs/{id}` (2 s).

## Schriften

Die Presets nennen `Arial`; Arial ist nicht redistributierbar. Im Image liegt
`fonts-liberation` + eine fontconfig-Regel, die `Arial` auf `Liberation Sans`
abbildet (metrik-kompatibel). Der Dienst meldet die tatsächlich verfügbaren
Familien in `/health`, damit Abweichungen sichtbar sind statt still zu passieren.

## Sicherheit

- Keine Shell: ffmpeg wird per Argumentliste (`subprocess.run(list)`) gestartet,
  keine Nutzereingabe landet in einer Kommandozeile.
- Pfade werden ausschließlich aus der Job-ID konstruiert (`<ULID>`), nie aus
  Nutzereingaben; Dateinamen werden auf `[A-Za-z0-9._-]` beschränkt.
- Upload-Grenzen (ASS ≤ 2 MB, Video ≤ 2 GB), Zeitlimit pro Job (Konfiguration).
- Die `.ass`-Datei ist Nutzerinhalt: sie wird von libass gelesen, nicht
  ausgeführt. Templates aus Change 193 Phase 3 laufen weiterhin durch unsere
  Sandbox, bevor sie hier ankommen.

## Entscheidungen

1. **Warum MOV *und* WebM?** Schnittprogramme wollen ProRes 4444, Browser und
   schnelle Weitergabe wollen WebM — der Zusatzaufwand ist je ein Encoder.
2. **Warum kein Browser-Rendering (ffmpeg.wasm)?** Für 1080p ist das um
   Größenordnungen zu langsam und würde den Rechner des Nutzers blockieren.
3. **Warum 1 Job?** CPU-intensiv; parallel würde die Transkription ausgebremst.
   Die Warteschlange ist im Dienst, nicht in der Webapp (der Dienst kennt seine Last).
4. **Kein GPU-Zwang:** VP9-Alpha und ProRes 4444 haben keinen nutzbaren
   Hardware-Pfad; x264 ist auf CPU ausreichend schnell.
