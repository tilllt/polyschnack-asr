# Tasks — Change 022 (ps-post: Punctuation + Truecasing)

## Phase 0 — Dokumentation (dieser Change)
- [x] proposal.md: Verhaltens-Delta (ps-post + 3. Dienst, Pipeline, Übergang)
- [x] design.md: Supervisor-Design, Optionen-Vergleich, segmentweise Anwendung
- [x] specs/postprocessing/spec.md + specs/transcription/spec.md (Deltas)
- [ ] OpenSpec-validieren, Commit + Push auf main, CI prüfen

## Phase 1 — ps-post-Container (Supervisor: Diar + Align + Punc)
- [ ] **Verifikation CrispASR-Binding:** `docs/bindings.md` lesen;
      Testskript: `crispasr.PuncModel` auf Beispieldatei laden,
      Text-in/Text-out, Truecaser-Verfügbarkeit klären (lstm vs.
      auto-Fallback). Ergebnis in design.md ergänzen.
- [ ] punc-dienst (NEU): FastAPI-Endpunkt `POST /v1/text/punctuate`
      `{text, language}` → `{text}`; `GET /health`; CPU-only;
      GGUFs (fullstop-punc, truecaser-de) beim Build ins Image
      (KEINE Laufzeit-Downloads).
- [ ] Supervisor: bestehendes ps-post-Image aus 020 Phase 3
      (crispr-diar + crispr-align) um den punc-dienst erweitern —
      drei Prozesse, je eigenes `/health`, Ausfall isoliert.
- [ ] `compose.yml`: Service `ps-post` (CPU-only, kein nvidia-Runtime);
      Webapp-Env `POLYSCHNACK_PS_POST_URL` (Default leer).

## Phase 2 — Webapp-Integration
- [ ] `service.py::process_recording`: nach ASR-Stufe ps-post-Schritt
      (Diar/Align wie gehabt + punc je Segment), VOR LLM-Template;
      `postprocess_status` am Recording
      (`none|punc-done|punc-fallback`).
- [ ] Fehlerverhalten: punc-Timeout/nicht erreichbar → roher Text +
      `postprocess_status="punc-fallback"` (sichtbar, kein stiller
      Fehler); Transkription bleibt `done`.
- [ ] Tests: Unit (punc-Client mit Mock), Integration (ps-post gegen
      Testtext inkl. Segment-Erhalt), Fallback (ps-post down → roher
      Text + Flag), bestehende Suite grün.

## Phase 3 — Übergang + Deploy
- [ ] Deploy-Images (moonshine/canary/pk-cpp): `--punc-model`/
      `--truecase-model` aus Dockerfile-ENV/onstart entfernen —
      erst NACH ps-post-Deploy (User deployt von Harbor).
- [ ] Deploy-Runde: ps-post + Webapp bauen, Env setzen, Smoke-Test
      (Transkription mit/ohne punc, Fallback-Flag), CI-Check.
- [ ] Align-CPU-Messpunkt (020 Phase 3) bleibt offen — entscheidet
      CPU-only-Instanzen für ps-post.

## Nicht vorgesehen (hier)
- Dispatcher-Anbindung von ps-post → Change 020 (Queue-Stufen,
  Remote-Instanzen).
- Sprach-Erkennung/LID → bleibt in der ASR-Stufe (CrispASR `-l auto`).
