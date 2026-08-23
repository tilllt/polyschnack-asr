# Change 098 — Health-Scan räumt Altbestand-MP3-Previews auf

**Status:** Implementiert, Commit folgt
**Anlass:** User-Frage 23.08.: „Beim nächsten deploy checkst du ob alle Files
die richtige Preview haben, generierst sie falls nicht, räumst nicht genutzte
alte Previews auf?"

## Ist-Zustand (bereits vorhanden)
- Der Health-Scan (`run_health_scan`, läuft als Hintergrund-Thread beim
  App-Start + in Intervallen) stellt die `<stem>_preview.opus`-Sidecar sicher:
  fehlende/kaputte Previews werden erzeugt/regeneriert (Change 096-Konvention).
- Die alten `<stem>_preview.mp3`-Dateien (64-kbps-MP3-Ära) blieben dagegen
  unaufgeräumt auf der Platte.

## Änderung (recording_health.py)
Neue Funktion `_sweep_legacy_mp3_previews(session, audio_dir)`, aufgerufen am
Ende jedes `run_health_scan`:
- Rekursiver glob (`**/*_preview.mp3`) über alle Audio-Unterordner
  (anon/user/restore)
- Löscht eine Alt-MP3 nur, wenn das neue `<stem>_preview.opus`-Gegenstück
  bereits existiert und > 0 Bytes hat (der reguläre Scan stellt es vorher
  sicher)
- Stellt einen veralteten `preview_path`-DB-Zeiger auf die `.opus`-Konvention
  um (sonst liefert der Preview-Endpoint nach dem Löschen 404)

## Pitfall (getestet)
`Path.glob("*_preview.mp3")` ist NICHT rekursiv — Recordings liegen in
Unterordnern. Erst `**/*_preview.mp3` findet die Altbestände.

## Tests
`test_health_scan_raeumt_legacy_mp3_preview_auf` (echte sine-WAV wie der
bestehende Preview-Test, kaputte Opus + Alt-MP3 + veralteter DB-Zeiger →
Scan: MP3 weg, Zeiger auf Opus). Bestehender Preview-Test weiter grün.
