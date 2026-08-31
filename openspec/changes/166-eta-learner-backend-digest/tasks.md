# Change 166 — Tasks

- [x] Befund: rtfestimate-DB der Box — alle `digest=None`; Code-Audit:
      `ingest_job_sample` ohne digest (service.py ~2784).
- [x] `_backend_image_digest(backend)` in service.py (DockerProxyClient,
      Label com.docker.compose.service → ImageID).
- [x] `process_recording`: digest nur bei `asr:`-Phasen übergeben.
- [x] Unit-Tests (Mock) in webapp/tests/test_backend_digest.py.
- [ ] Lokale Tests grün (test_learner_store + test_backend_digest).
- [ ] openspec/change 166 committen, push main, CI grün.
- [ ] Live: nächster Backend-Deploy invalidiert `asr:`-Historie
      (digest-Spalte gefüllt).
