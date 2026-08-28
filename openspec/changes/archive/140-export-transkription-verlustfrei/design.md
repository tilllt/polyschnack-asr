# Change 140 — Design-Entscheidungen (Transkription & Export verlustfrei)

## 1. Warum die Text/Wort-Invariante die richtige Wurzel-Heilung ist

Der Desync entsteht, weil Text (ASR) und Wörter (Aligner) aus ZWEI Quellen
kommen und die Zuordnung (apply_aligned_words) NUR nach Startzeit läuft.
Jede punktuelle Korrektur (nur Export, nur Anzeige) lässt die zwei Quellen
weiter divergieren. Die Invariante `join(words) == text` ist die einzige
Garantie, dass nichts verschluckt/erfunden wird — erzwungen an den zwei
Stellen, wo Wörter geschrieben werden:

1. `_run_align_phase` (nach dem Anwenden der Aligner-Wörter) — heilt die
   Aligner-Zuordnung sofort.
2. `update_result` (vor dem Persistieren) — Sicherheitsnetz für ALLE
   Pfade, auch ohne Aligner.

Der Text ist die unantastbare Wahrheit (vollständiger ASR-Text). Die
Wörter werden angeglichen — nie umgekehrt (das würde Text verlieren).

## 2. Heilung via vorhandenem `_align_words` (Change 010, LCS)

Kein neuer Algorithmus: `_align_words(old_words, text, start, end)` macht
genau die Angleichung — 1:1 bei gleicher Wortzahl (Zeiten exakt),
LCS bei Einfügen/Löschen (Matches behalten Zeiten, neue interpolieren),
Gleichverteilung als Fallback (< 50 % Matches — konsistent statt
fehlerhaft). override-Flags (Change 137) überleben Matches.

## 3. Export-Schutz als zweite Verteidigungslinie

Sollte trotz Invariante ein Alt-Stand oder ein Pfad ohne Reconcile
durchrutschen, verliert `resegment_by_duration` keinen Text mehr:
Bucket-Text proportional aus dem Segment-Text (Zeichen × Zeitanteil),
c1 auf der letzten Wortgrenze VOR der proportionalen Position (kein
Wort-Split), der letzte Bucket bekommt den Rest bis zum Text-Ende.
Backend und Frontend identisch (Anzeige == Export).

## 4. Speaker-Key: vollständiges Parsen statt Substring

Die GUI zeigt `SPEAKER_01` als „01" (bekannter Zusammenhang). Der Key
parst die Nummer VOLLSTÄNDIG: `SPEAKER_`-Präfix + komplette Ziffernfolge
(`SPEAKER_11` → 11, nie 1), nackte Zahl (`01`/`1` → 1), einzelner
Buchstabe (B → 1). Alles andere → kein Match. Kein Regex-Substring, kein
Buchstaben-Fallback auf den ersten Buchstaben des Gesamtstrings (der
„SPEAKER_A" fälschlich als S → 18 gematcht hätte).

## 5. Abgrenzung

- Kein Backfill: Bestehende desyncte Recordings kann der User per
  Re-Align heilen (der neue Code läuft dann auch dort).
- Re-Diarize (nur speaker) und Text-Edit (Change 139, Wörter werden
  bereits mitgebaut) sind konsistent per Konstruktion.
