# Tasks — Change 033 (Backend-Ressourcen-Requirements)

- [x] Backend-Definitionen geprüft (`/opt/data/scripts/start_timing_vast.py`, BACKENDS-Tabelle)
- [x] Prüfung: keine bestehenden Requirements-Dateien (Recherche 20.08.)
- [x] `docs/benchmark/requirements/README.md` — Übersicht + Methodik
- [x] Requirements-Datei je Backend (8): ps-pk-onnx, crispr-pk-cpp, crispr-qwen3,
      crispr-ark, crispr-moonshine-de, crispr-canary, whisper-large-v3, voxtral-mini-realtime
- [x] Modellgrößen belegt: HF-HEAD (Content-Length) 20.08.
- [x] Image-Größen belegt: Harbor (whisper 2,51 GB), Docker Hub (vllm 10,53 GB)
- [x] Runner-Patch: `VAST_GPU_PREF` + `VAST_MAX_PRICE` env-übersteuerbar
      (Default unverändert 3060/4070, 0,35 $/h)
- [x] Alt-Instanzen aufgeräumt: 48120442, 48133299, 48171249, 48172735 (Destroy)
- [ ] 207er-Nachlauf whisper-large-v3 (frische Instanz, Hintergrund, läuft)
- [ ] 207er-Nachlauf voxtral-mini-realtime (VAST_GPU_PREF 3090/4090, läuft)
- [ ] Ergebnis-JSONs prüfen + Rangliste (6 Backends) final zusammenstellen
- [ ] CI nach Push prüfen und melden
