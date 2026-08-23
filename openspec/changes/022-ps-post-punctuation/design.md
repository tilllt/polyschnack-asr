# Design — Change 022 (ps-auxiliary: Punctuation + Truecasing)

## ps-auxiliary-Container: drei Prozesse unter einem Supervisor

Der `ps-auxiliary`-Container aus Change 020 (Supervisor: crispr-diar +
crispr-align) bekommt als dritten Dienst den Formatierungs-Dienst:

```
ps-auxiliary (1 Image, Supervisor)
├── crispr-diar     :5098  Diarization     (CPU-only, belegt PR #364)
├── crispr-align    :5099  Forced Aligner  (ggml-hybrid, CPU-Messpunkt offen)
└── punc-dienst     :5100  Punc+Truecase   (CPU-only, NEU — dieser Change)
```

Alle drei Dienste sind unabhängig erreichbar (je `/health`); die Webapp
ruft sie je nach Job-Flags an (Diarize, Aligner, Punc). Der Supervisor
startet alle drei; ein Dienst-Ausfall lässt die anderen weiterlaufen.

## Entscheidung: CrispASR-Binding statt punc im ASR-Server

| Option | Bewertung |
|---|---|
| **A: CrispASR-Python-Binding `PuncModel` als punc-dienst** | Gewählt. README (CrispStrobe/CrispASR, v0.8.28) belegt: Punc-Restoration „also available via Python/Rust/Dart wrappers (`crispasr.PuncModel`)". Lädt GGUF direkt, Text-in/Text-out, CPU-fähig (XLM-RoBERTa-large q4_k ≈ klein), kein Audio nötig. Ein Dienst für alle Backends. |
| B: punc im ASR-Server lassen (Status quo) | Verworfen: Duplikation über Images, HF-Download bei jeder frischen Instanz (Startzeit-Confounder, hängend beobachtet), Post-Processing im ASR-Container. |
| C: transformers/XLM-RoBERTa als eigener Dienst | Verworfen: schwergewichtig (PyTorch), dupliziert die GGUF-Infrastruktur von CrispASR, kein Vorteil gegenüber A. |

**Verifikationspunkt beim Bau:** `docs/bindings.md` des CrispASR-Repos
prüfen — ob `PuncModel` auch den Truecaser (`--truecase-model lstm`,
truecaser-de, 3,2 MB, 97,9 % F1 laut README) mitlädt oder als separater
Schritt nötig ist. Fallback: `auto`-Truecaser (statistisch, 9 MB) oder
eigener kleiner Dienstschritt im selben Prozess.

## Segmentweise Anwendung (Timestamps erhalten)

Der punc-dienst erhält pro **Segment** einen Text (nicht das
Gesamttranskript):
- Satzzeichen/Großschreibung ändern die Wortreihenfolge nicht → die
  Segment-Grenzen, Wort-Timestamps und Sprecher-Zuordnung der ASR-/
  Aligner-Stufe bleiben gültig.
- Diarisierte Segmente behalten ihre Sprecher-Zuordnung.
- API: `POST /v1/text/punctuate` `{text, language}` → `{text}`;
  die Webapp iteriert über die Segmente. Language optional
  (Default: de).
- Sehr kurze Segmente (< 3 Wörter): Reranker-Qualität prüfen,
  ggf. unverändert durchreichen (offene Frage).

## Pipeline-Reihenfolge

`Upload → ASR (roh) → ps-auxiliary (Diar + Align + Punc) → LLM-Template
(opt-in, Change 005) → Version/Export`

Begründung: Das LLM-Template (Zusammenfassung etc.) arbeitet auf
formatiertem Text — sonst müsste es punc-fehlerhafte Groß-/Kleinschreibung
erst selbst reparieren.

## Übergang ohne Verhaltensbruch

1. **Jetzt:** Webapp bekommt die Stufe hinter `POLYSCHNACK_PS_POST_URL`
   (Default: nicht gesetzt → ASR-interne punc/truecase-Args bleiben
   aktiv). Kein Verhaltensbruch im Ist-Betrieb.
2. **ps-auxiliary deployed:** Env setzen → Stufe aktiv; ASR-Images verlieren
   die Args (separater Schritt, mit Deploy-Runde).
3. **Fehlerfall:** punc-dienst down → roher Text +
   `postprocess_status="punc-fallback"` am Recording (sichtbar in
   UI/API, kein stiller Fehler); Transkription bleibt `done`.

## Ressourcen

- punc-dienst: CPU-only (kein `runtime: nvidia`); punc- und
  truecase-Modelle sind klein. Diar/Align wie in 020 geplant.
- Modell-Cache: GGUFs einmalig ins Image brennen (Build-Zeit), damit
  keine Laufzeit-Downloads entstehen (Lektion aus dem Startzeit-
  Benchmark).

## Offene Fragen

- Sprach-Steuerung: fullstop-punc kann EN/DE/FR/IT — Sprache pro Request
  oder aus ASR-Metadaten (`language`-Feld) übernehmen?
- Align-CPU-Messpunkt (020 Phase 3) entscheidet, ob ps-auxiliary auf
  CPU-only-Instanzen laufen kann — betrifft den ganzen Container.
