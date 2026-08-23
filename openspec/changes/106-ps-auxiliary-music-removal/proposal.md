# Change 106 — ps-auxiliary: Umbenennung + Music-Removal-Optionen (htdemucs / mel-band-roformer)

## Status
- **Stand:** 2026-08-23
- **Phase:** Entwurf (noch keine Umsetzung)

## Problem
1. **Name `ps-post` existiert nur in Plänen.** Change 020/022 definieren einen
   `ps-post`-Supervisor-Container (Diar + Align + Punc) — gebaut wurde er nie:
   kein Ordner, kein compose-Service, kein Image. Real laufen getrennte Dienste
   (`crispr-diar`, `crispr-align`, Webapp ruft beide als Clients). Der Name soll
   in `ps-auxiliary` geändert werden, damit er das tatsächliche Aufgabenspektrum
   (Diar, Align, Punc, künftig Source Separation) abdeckt.
2. **Gesang mit Musik kann der Aligner nicht verorten** (saisoncouplet,
   Recording 295): Forced-Aligner liefert 0 Wort-Timestamps → ehrliches
   `skipped` (Change 101). Music-Removal als **Pre-Processing** (Vocals-Stem
   extrahieren) soll ASR und Aligner auf Gesang verbessern.

## Analyse / Befund
- `grep "ps-post"`: nur OpenSpec 020/022 (5 Dateien) + 6 Skill-Referenzen —
  **kein Code**. Umbenennung ist reine Doku-Arbeit.
- **CrispASR kann Source Separation nativ:** `--separate` mit Backends
  `htdemucs` (4 Stems) und `mel-band-roformer` (vocals/other), inkl.
  `--stems`, `--sep-output-dir`; im gebauten Binary verifiziert
  (`build-fix/bin/crispasr --list-backends`: beide mit `separate: Y`,
  `auto-dl: Y`).
- **Beide Modelle liegen als GGUF auf HF (cstr), MIT-Lizenz, EU-AI-Act-Notiz:**
  - `cstr/htdemucs-GGUF`: F16 81 MB / Q8_0 53 MB / Q4_K 38 MB
  - `cstr/mel-band-roformer-vocals-GGUF`: **nur F16 (~436 MB)**, kein Q8
- **Settings-Fläche existiert:** TranscriptionRun-Settings (Change 099/103) mit
  `enable_vad`, `enable_noise_reduce`, `enable_enhance`, `enable_punctuation`
  usw. — ein `separate_backend`-Feld passt ins Muster.
- **Risiko CPU:** mel-band-roformer-F16-Forward auf CPU-only-Instanzen ist
  scalar-Fallback → langsam. Auf der Box (CUDA) unkritisch; Performance messen.

## Lösung
1. **Umbenennung `ps-post` → `ps-auxiliary`** (nur Doku): Texte in
   `openspec/changes/020…/022…` und betroffenen Skills. Kein Code-Refactor.
   Der geplante Supervisor-Container aus 022 **wird weiterhin nicht gebaut** —
   Diar/Align/Punc bleiben getrennte Dienste (wie real umgesetzt).
2. **Neuer Dienst `crispr-sep`** (Port 5100, nur intern im Compose-Netz, kein
   expose) nach dem Muster von `crispr-align`:
   - Image: `${REGISTRY:-ghcr.io/tilllt}/polyschnack-asr-sep:latest`
   - Volume `./DATA/models:/models`, Entrypoint lädt fehlende GGUFs von HF
     (htdemucs-f16/q8_0 + mel-band-roformer-vocals-f16)
   - CrispASR-Binary (Fork-Stand mit htdemucs-Parity, vorher Smoke-Test)
   - Endpoint `POST /separate` (audio, backend: `htdemucs|melband`) →
     `<input>_vocals.wav` zurück; Fehler/leere Ausgabe → 422 mit Grund
3. **Webapp-Anbindung** (analog AlignerClient):
   - Settings-Feld `separate_backend: str = "none"` (`none|htdemucs|melband`)
     im TranscriptionRun-Settings-Muster (099/103)
   - Pipeline: Upload → **optional separate (vocals als ASR-Eingabe)** → ASR →
     Align; Original-Audio bleibt unverändert
   - **Fehlerpfad ehrlich:** separate down / liefert nichts → Weiter mit
     Original-Audio, Status vermerkt den Grund (Muster Change 101, kein
     Fake-„done")
4. **Keine automatische Aktivierung:** Default `none`; pro Recording wählbar.

## Verifikation
- Smoke-Test `--separate` **beider** Backends gegen 5-s-Testmix (Gesang + Musik)
  auf der Box und lokal; Ausgabe-Plausibilität (vocals-RMS vs. other).
- ASR-WER mit/ohne separate auf einem kleinen Gesangs-Testset.
- **saisoncouplet (Recording 295):** Re-Align mit separate→vocals als
  Eingabe — Ziel: Aligner liefert Wort-Timestamps statt `skipped`.
- Unit (separate_client mit Mock), Integration (crispr-sep gegen Testmix),
  Fallback (crispr-sep down → Original-Audio, Status-Hinweis).
- 90-min-Performance: GPU (Box) vs. CPU-only-Instanz messen (htdemucs F16).

## Ausblick
- Deploy-Runde: Image bauen (Harbor), compose `crispr-sep`, Settings-Feld,
  Live-Test saisoncouplet.
- Optional später: Q8-Konvertierung von mel-band-roformer (cstr anfragen oder
  selbst), `separate` auch als reine Align-Vorstufe ohne ASR-Umweg.
- Kein Supervisor-Zusammenbau (bewusst out of scope — kein Ops-Vorteil, dafür
  Deploy-Risiko; getrennte Dienste bleiben).
