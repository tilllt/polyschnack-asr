# aligner-service — Forced-Aligner (Karaoke-Wortzeiten)

Schlanker HTTP-Wrapper (stdlib) um den CrispASR-Forced-Aligner
(qwen3/tada/wav2vec2). Bekommt pro Request ein Segment-Audio + den
Segment-Text und liefert `[{start, end, word}]`.

## Wortzeit-Invarianten (Change 159, 2026-08-30)

Der qwen3-forced-aligner liefert zwei systematische Artefakte, die den
Karaoke-View kaputt machen — beide werden in `_resolve_zero_duration`
geheilt (nach `_energy_refine`):

1. **Letztes Wort eines Segments wird an die Audio-Kante gequetscht**
   (0-Dauer / minimale Restzeit) → 80-ms-Kollaps → Karaoke überspringt
   das Wort. Live gemessen: 207/1809 Prod-Segmente (11,4 %), 140× exakte
   0,08-s-Signatur. Fix: **Mindestdauer 0,3 s** fürs letzte Wort (Start
   rückwärts gezogen, begrenzt durch den Vorgänger-Start; Überlappung
   mit dem Vorgänger ist akzeptabel).
2. **0-Dauer-Ketten** (mehrere Wörter auf identischer 80-ms-Klasse, z.B.
   4× „ja" auf derselben Zeit) → Karaoke markiert gleichzeitig (wirkt
   wie „doppelte Textpassagen"). Fix: **Monotonie-Invariante** — kein
   Wort startet vor dem Vorgänger-Ende; Wörter mit `end <= start`
   bekommen `end = start + 0.08`.

**A/B-Befund (falsifizierte Hypothese):** Ein End-Puffer beim Audio-
Schnitt (`-to seg_end + 0.5 s`) hilft NICHT — der Aligner legt das letzte
Wort ans gepufferte Audio-Ende (wurde schlechter: 12.08→12.16 vs.
12.72→12.74). Die Korrektur gehört in die Wort-Verarbeitung, nicht in
den Schnitt.

Tests: `tests/` (unittest) — `_energy_refine`-Regionen, Parser, die zwei
Invarianten inkl. Regressionen. Ausführen: `python -m pytest tests/`.

## Betrieb

- Port 5099, Endpoint `POST /v1/audio/align` (multipart: file, text,
  lang, method).
- `GET /health` + `GET /status` (Heartbeat: active, last_line,
  progress_pct — von der Webapp gepollt, ehrliche Werte).
- Modell-Downloads (qwen3-FA, TADA, wav2vec2) laufen im Entrypoint mit
  Selbstheilung (siehe `entrypoint.sh`).
