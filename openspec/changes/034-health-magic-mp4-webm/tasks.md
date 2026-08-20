# Tasks — Change 034 (Self-Healing Magic-Fix)

- [x] Fehlermeldung analysiert: Magic `\x00\x00\x00\x1c` = ISO-BMFF-Box-Size (28) → MP4/M4A
- [x] `_looks_like_audio()`: Präfix-Magic + ISO-BMFF-Typ an Position 4 (ftyp/moov/mdat/free/wide/styp/skip/pdin)
- [x] WebM/EBML (`\x1a\x45\xdf\xa3`) + AAC-ADTS (`\xff\xf1`/`\xff\xf9`) ergänzt
- [x] `#EXTM3U` aus Magic-Liste entfernt
- [x] User-Korrektur: `_is_healthy()` — unbekannte Magic → ffmpeg-Konvertierung zu `<stored>.conv.mp3` (Sidecar); failed nur wenn ffmpeg die Datei nicht lesen kann
- [x] `heal_false_failures()`: failed + Health-Fehlermeldung + jetzt gültige Datei (Magic ODER ffmpeg-lesbar) → done/uploaded
- [x] moov-Fall bereits via Change 011 gelöst (faststart-Remux) — unberührt, dokumentiert
- [x] Tests: M4A/WebM/AAC/WAV/MP3/OGG gültig, Müll weiterhin kaputt, AIFF → Sidecar statt failed, ffmpeg-unlesbar → failed, Fehldiagnose geheilt, echter Schaden bleibt failed
- [x] Lokal: pytest test_change014_storage_health_title.py → 19 passed
- [ ] Commit + Push → CI-Build (webapp-Image)
- [ ] CI-Pipeline prüfen und melden
- [ ] Nach Deploy: ersten Health-Scan auf der Box beobachten (Selbstheilung)
