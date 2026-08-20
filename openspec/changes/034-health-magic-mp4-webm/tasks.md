# Tasks — Change 034 (Self-Healing Magic-Fix)

- [x] Fehlermeldung analysiert: Magic `\x00\x00\x00\x1c` = ISO-BMFF-Box-Size (28) → MP4/M4A
- [x] `_looks_like_audio()`: Präfix-Magic + ISO-BMFF-Typ an Position 4 (ftyp/moov/mdat/free/wide/styp/skip/pdin)
- [x] WebM/EBML (`\x1a\x45\xdf\xa3`) + AAC-ADTS (`\xff\xf1`/`\xff\xf9`) ergänzt
- [x] `#EXTM3U` aus Magic-Liste entfernt
- [x] User-Korrektur: `_ensure_healthy()` — unbekannte/nicht-native Magic → ffmpeg-Konvertierung zu MP3; stored_path-Umbiegung, Original als `.orig<ext>` (Change-018-Konvention); failed nur wenn ffmpeg die Datei nicht lesen kann
- [x] Native Formate (WAV/MP3/FLAC/MP4/M4A) → keine Konvertierung (direkt verarbeitbar, User-Vorgabe)
- [x] Preview-Sidecar (`<stem>_preview.mp3`) sicherstellen/regenerieren (User-Vorgabe)
- [x] `heal_false_failures` → inline-Heilung im Scan (failed + Health-Fehlermeldung + jetzt gültige Datei → done/uploaded)
- [x] moov-Fall bereits via Change 011 gelöst (faststart-Remux) — unberührt, dokumentiert
- [x] Tests: M4A/WebM/AAC/WAV/MP3/OGG gültig, Müll weiterhin kaputt, AIFF → MP3 + Original archiviert, OGG (nicht-nativ) → MP3, Preview regeneriert, ffmpeg-unlesbar → failed, Fehldiagnose geheilt, echter Schaden bleibt failed
- [x] Lokal: pytest test_change014_storage_health_title.py → 21 passed
- [ ] Commit + Push → CI-Build (webapp-Image)
- [ ] CI-Pipeline prüfen und melden
- [ ] Nach Deploy: ersten Health-Scan auf der Box beobachten (Selbstheilung)
