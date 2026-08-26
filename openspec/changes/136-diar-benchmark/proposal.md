# Change 136: Diarization-Benchmark-Suite (deutsches Testset)

## Problem

Der Diar-Tab (Change 135) zeigt „noch keine Daten". Es gibt keinen
Diarization-Benchmark — dabei ist die Sprecher-Zuordnung („wer spricht wann")
ein Kernfeature von PolySchnack (Meeting-Protokolle) und aktuell nur
subjektiv bewertet („unbenutzbar schlecht", Teamtreffen 26.08.).

## Ziel

Eine Diarization-Benchmark-Suite nach dem Vorbild der VAD-Suite:

1. **Deutsches Testset aus einem Standard-Korpus** — Randbedingung User
   (26.08.): **NUR Deutsch interessiert; der ASR-Benchmark ist bereits
   relativ gut** — kein englischer Ersatz.
2. Kandidat: **CALLHOME German** (LDC97S43, TalkBank-DOI 10.21415/T56P4B) —
   unscripted Telefongespräche zwischen deutschen Muttersprachlern,
   ~100 Teilnehmer, Sprecher-Labels, als HF-Dataset
   `diarizers-community/callhome` (deu-Subset, bereits mit
   timestamps_start/end + speakers, kompatibel zu pyannote-Diarizers).
   VoxConverse/AMI verworfen: englisch.
3. **Metriken:** DER (Diarization Error Rate = Missed Speech + False Alarm +
   Speaker Confusion) bzw. Jaccard-Ähnlichkeit je Segment, Sprecherzahl-
   Abweichung, RTF.
4. **Methoden unter Test:** foxnose (WeSpeaker-Embedder + Clustering, Default),
   pyannote-seg-3.0 (GGUF), vad-turns (Baseline ohne Modell) — alle laufen
   bereits im crispr-diar-Container.
5. **Submission:** wie VAD (Package-Hash, Container misst + submittet mit
   HMAC) oder direkt über den diar-Container; Ergebnisse in latest.json
   (kind="diar") → Diar-Tab füllt sich.
6. **Anhörbar:** Diar-Samples mit Player im Diar-Tab (wie VAD/ASR).

## Lizenz-Hinweis

**ENTSCHEIDUNG 26.08. (User): VoxPopuli-de statt CALLHOME.** CALLHOME German
(TalkBank/HF) ist **CC-BY-NC-SA-4.0** und **gated** (401 ohne Token / 403 mit
Token) — für ein öffentliches GitHub-Release (PolySchnack ist kommerziell)
ungeeignet. Recherche alternativer deutscher Korpora: KALAKA/KALLIS nicht
frei verfügbar (nur ELRA/Institutionen), ALLIES französisch, Fischbach-2024
nur Dialekt-Identifikation. Gewählt: **VoxPopuli-de** (facebook/voxpopuli,
**CC0-1.0 / Public Domain**, nicht gated) — echter Parlamentsrede-Korpus mit
Sprecher-IDs je Segment. Mehrsprecher-Calls werden **synthetisch** gemixt
(Segmente verschiedener Sprecher aneinandergereiht, deterministisch Seed 42)
→ exakte GT aus der Konstruktion (kein Label-Rauschen). Nachteil akzeptiert:
keine natürlichen Überlappungen/Telefonqualität, aber vollwertig für die
Sprecher-Zuordnungs-Messung (DER).

## Nicht-Ziel

- Kein neues Diarization-Modell-Training (nur Benchmarking bestehender
  Methoden im Stack).
- Keine Änderung des ASR-Testsets (das ist „relativ gut" — bleibt).
- Keine natürlichen Mehrsprecher-Aufnahmen (Überlappung/Telefon) — bei
  Bedarf später als Erweiterung (CALLHOME intern lizenzierbar).

## Kontext

- Diar-Tab-Platzhalter: Change 135 (SuiteExplainer.diar verweist auf 136).
- Diar-Container: `crispr-diar` (foxnose/pyannote/vad-turns, mono-tauglich,
  embedder=auto, CACHE-DIR aufs Modell-Volume).
- VAD-Suite als Vorlage: `benchmarks/vad/` (Package, Runner, Selfservice,
  vast-Runner), `_vad_summary` in benchmark_service.py.
- Stand: Teamtreffen-Re-Diarisierung unbrauchbar (User 26.08.) — Benchmark
  schafft die Evidenz, ob foxnose das Maximum kann.
