# Change 200 — Render-Dienst für Untertitel-Videos (inkl. Alpha)

## Warum

Change 193 liefert animierte `.ass`-Untertitel zum Download; das Einbrennen war
als „Phase 4" geplant und ist **nicht gebaut**. Der Endpunkt antwortet deshalb
mit `503 render_unavailable` und der Dialog zeigt nur einen Hinweis. Nutzer
wollen aber ein fertiges Video herunterladen — und ausdrücklich auch ein
**Untertitel-Video mit Alphakanal** (transparenter Hintergrund), das sich im
Schnittprogramm über das eigene Video legen lässt.

## Was sich ändert

- Neuer optionaler Container **`ps-render`** (`render-service/`): ffmpeg + libass
  + Schriften, eigener kleiner Job-Dienst mit **echtem Fortschritt**.
- Formate (Capability-getrieben, der Dienst meldet, was er kann):
  - `burn_mp4` — H.264/AAC, Untertitel eingebrannt über Hintergrundfarbe
    (Aufnahmen sind oft reines Audio) 
  - `alpha_webm` — VP9 **mit Alpha** (`yuva420p`), nur Untertitel → Overlay-Asset
  - `alpha_mov` — ProRes 4444 **mit Alpha** (`yuva444p10le`) → Schnittprogramm-Standard
  - `alpha_png` — PNG-Sequenz (ZIP), universell, große Dateien (optional, Phase 3)
- Webapp: `export/render_client.py` spricht den Dienst an; `render_available`
  kommt aus dessen `/health`; neue Endpunkte für Job-Start, Status und Download.
- GUI: im Export-Dialog erscheint die Format-Auswahl **nur, wenn der Dienst
  läuft** — plus echter Fortschrittsbalken (Prozent aus ffmpeg), Abbrechen und
  Download.
- Betrieb: Compose-Service im Profil `render`, eigenes Image in CI, Aufräumen
  nach 24 h.

## Auswirkungen

- Kernel/Webapp läuft weiter ohne den Dienst (unverändert 503 + Hinweis).
- Zusätzliche Last: ein Render-Job gleichzeitig (CPU-intensiv), Warteschlange im
  Dienst, kein GPU-Zwang.
- Neue Abhängigkeit nur im Render-Image (ffmpeg/libass/Schriften), nicht in der Webapp.
- Admin-Doku: Abschnitt „Video-Export (optionaler Render-Dienst)".
