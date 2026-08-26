# Tasks — Change 130

- [x] Wurzelursache belegt: Server behandelt `diarize_embedder` als Dateipfad,
      löst Registry-Alias `wespeaker` nicht auf (`failed to open GGUF file
      'wespeaker'`) — reproduziert auf v0.8.28-ort-poc1 (Box-Artefakt) UND
      v0.8.29 (lokal); Gegenprobe `auto` → lädt Wespeaker-GGUF, 6 Speaker
- [x] Box-Log (User) bestätigt: `gguf_init_from_file: failed to open GGUF file
      'wespeaker'` — Fix 126 war deployed, sendete den kaputten Alias
- [x] Fix: `DIARIZE_FOXNOSE_EMBEDDER`-Default `wespeaker` → `auto`
      (webapp/app/config.py)
- [x] Test angepasst: `test_diarize_foxnose_sendet_embedder_auto` — erwartet
      `auto`, verbietet `wespeaker`
- [x] Doku: docs/diarization.md (Warnbox Change 130), docs/configuration/env.md
- [x] Tests grün (test_diarize_device.py + Diarize-Suite)
- [x] Commit + Push + CI-Report
