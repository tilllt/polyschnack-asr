# Change 166 — ETA-Learner: Backend-Digest an den Ingest durchreichen

**Status:** Proposed

## Befund (2026-08-31, ETA-Learner-Audit)

- `learner_store.ingest_job_sample` hat einen `digest`-Parameter, und der
  `RtfLearner` invalidiert die gelernte Historie bei Digest-Wechsel
  (Change-085-Regel: Backend-Image-Update ⇒ alte Stichproben verwerfen,
  getestet in `test_digest_invalidiert_asr_key`).
- ABER: `service.process_recording` ruft `ingest_job_sample(rec_id,
  phase_times, duration)` OHNE `digest` auf (service.py ~2784) →
  alle `rtfestimate`-Zeilen haben `digest=None` (Live-Befund auf der
  KI-Box). Nach einem Backend-Image-Wechsel (z. B. die CrispASR-
  Original-Images) würden Stichproben aus altem und neuem Image
  ungefiltert gemischt — die Invalidation greift nie.
- Rediarize/Align sind nicht betroffen (nur `asr:`-Keys tragen einen
  Digest; diar/align-Ingests ignorieren ihn laut learner_store).

## Lösung

1. Neue Funktion `_backend_image_digest(backend)` in `service.py`: holt
   über den bestehenden `DockerProxyClient` (`/containers/json`) die
   `ImageID` des Containers, dessen `com.docker.compose.service`-Label dem
   Backend-Namen entspricht. Die ImageID ist der Docker-config-Digest —
   stabil pro Image, wechselt bei Backend-Image-Update (genau das Signal,
   das der Learner braucht).
2. `process_recording` übergibt den Digest beim done-Ingest, wenn
   `asr:`-Phasen gemessen wurden.
3. Fehler/fehlender Container/fehlendes Backend → `None` (graceful, kein
   Invalidation, kein Fehler — Anti-Fake bleibt: nie raten).

## Tests

- Unit: `_backend_image_digest` mit gemocktem DockerProxyClient
  (Treffer per Label, unbekannt → None, Proxy-Fehler → None).
- Bestehend: `test_digest_invalidiert_asr_key` (Mechanik) bleibt grün;
  `test_learner_store.py` unverändert grün.
