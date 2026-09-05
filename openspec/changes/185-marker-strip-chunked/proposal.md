# Change 185 — End-Marker im Transkript/Export (Strip läuft nicht für chunked Streams)

**Status:** Deployed (2026-09-05, ba54e93, CI 4917 grün; Migration auf KI-Box ausgeführt + verifiziert)

## Befund (Live, prod KI-Box — DB-Beleg 2026-09-05)

User: „Beim Exportieren von Texten aus PolySchnack ist der End-Marker mit im
Text enthalten."

DB-Scan (recording/transcriptionresult/transcriptversion, Suffix-Prüfung):

- **REC 318** („Till Gespräch Heidberg Früh-Reha Mama", 510 s, ps-pk-onnx,
  fertig 2026-08-31) — Text endet: `…Dann danke ich Ihnen. Okay. Dankeschön.
  Tschüss. Seven, four, two, eight, one, six, zero, three, nine.`
- **REC 322** („Notizen für Gespräch Gollaleh Ahmadi", 1644 s, ps-pk-onnx,
  transkribiert 2026-09-03/05) — Text endet: `…Und an dem Punkt sind wir,
  glaube ich, nicht mehr. Seven, four, two, eight, one, six, zero, three,
  nine.`
- Dazu 2 transcriptionresult- und 9 transcriptversion-Zeilen derselben
  Aufnahmen (Restore/Versionen würden den Marker zurückholen).

Die Ziffernfolge 7-4-2-8-1-6-0-3-9 ist der TTS-Vollständigkeits-Marker aus
Change 147 (transcript_marker.wav, ans Audio-Ende gehängt) — er ist nie
Transkript-Inhalt und erscheint dadurch in jedem Export (txt/srt/vtt/
Templates/Backup) und im UI-Text.

## Root-Cause

`process_recording` (service.py, Change 147) hängt den Marker ab
`_TRANSCRIPT_MIN_S` (≥5 min) IMMER ans Audio — unabhängig vom Backend
(`marker_active`, Zeile ~2489). Das Entfernen (`_strip_transcript_marker`)
läuft aber NUR im Fallback-Zweig:

```python
elif marker_active and not result.get("chunked") and status == "done":
```

Chunked Streams (ps-pk-onnx transkribiert mehrchunkig, `total_chunks > 1`;
Vollständigkeit dort über die Chunk-Zählung bewiesen) überspringen den Strip
komplett → Marker-Text wird persistiert (segments + rec.text).

Warum nur 2 von 25 ≥5-min-Recordings betroffen sind: Transkriptionen vor dem
Change-147-Deploy (2026-08-28) haben nie einen Marker im Audio; neuere
Transkriptionen mit streaming=aus liefen über den nicht-chunked Pfad und
wurden gestrippt. Betroffen sind ausschließlich mehrchunkige Streaming-Runs
nach 147/154.

Zweiter Defekt (durch die DB-Belege sichtbar): Der Strip arbeitet
segmentweise mit Ganz-Segment-Pop (Zeit-Tail ODER `_marker_ratio >= 0.5`).
In beiden Belegen steht der Marker aber am ENDE eines gemischten Segments mit
echtem Text (`…nicht mehr. Seven, four, two, …` — Ratio ~0.1 bei langen
Segmenten, gar nicht erkennbar; oder `Okay. Dankeschön. Tschüss. Seven, …` —
Ratio 0.75, würde beim Pop den echten Abschied mitsamt Segment löschen).
Zusätzlich werden Marker-Wörter von der ASR mit Großschreibung/Interpunktion
transkribiert (`Seven, four, …`) — die bisherige `_marker_ratio` erkennt
`Seven` (groß) nicht (Token-Vergleich case-sensitiv gegen _MARKER_WORDS).

Dritter Befund (bei der Migrations-Verifikation): Die Segmente tragen
Wort-Timing-Listen (`words: [{start, end, word}]`), die die Marker-Wörter
ebenfalls enthalten — Bestands-Runs bauten sie aus dem ungestrippten Text.
Nur den Segment-Text zu trimmen ließe die Marker-Wörter in den
Wort-Timings stehen.

## Fix

### 1. Pipeline: Strip läuft IMMER bei aktivem Marker (auch chunked)

```python
elif marker_active and status == "done":
    audio_total_s = _probe_audio_duration(audio_bytes)
    segments, text, marker_found = _strip_transcript_marker(
        segments, text, audio_total_s,
    )
    # Zeit-Fallback NUR für nicht-chunked Backends (dort ist die
    # Chunk-Zählung der primäre Vollständigkeits-Beweis).
    if (not result.get("chunked") and not marker_found
            and not _transcript_complete(segments, audio_total_s)):
        … failed (Stream abgerissen) …
```

Vollständigkeits-Semantik bleibt identisch: truncated (Chunk-Zählung) →
failed wie bisher; nicht-chunked ohne Marker + Zeit-Lücke → failed wie
bisher; chunked + vollständig → nur noch Hygiene-Strip.

### 2. Suffix-Trim statt Ganz-Segment-Pop für gemischte End-Segmente

Neuer, reiner Helfer (kein schwerer Import — auch aus der Datenmigration
nutzbar): `_strip_marker_suffix(text) -> (text, found)`. Entfernt am
TEXT-ENDE einen Lauf aus ≥4 Ziffern-Tokens (Zahlwort inkl. engl./dt./pt.
Wortformen ODER Ziffern, case-insensitiv, Interpunktion/Leerzeichen
dazwischen tolerant) und lässt echten Text davor unangetastet:

- `…nicht mehr. Seven, four, two, eight, one, six, zero, three, nine.`
  → `…nicht mehr.`  (Marker weg, echter Inhalt bleibt — auch bei Ratio < 0.5)
- `Okay. Dankeschön. Tschüss. Seven, four, …` → `Okay. Dankeschön. Tschüss.`
  (kein Ganz-Segment-Pop mehr → Abschied bleibt erhalten)
- Einzelne Zahlen am Ende (`…die Antwort ist 42`) bleiben (Lauf < 4).

`_strip_transcript_marker` nutzt den Suffix-Trim je End-Segment (bis 4):
Segment-Text wird getrimmt; wird ein Segment dadurch leer → Segment fällt
(Ganz-Pop bleibt nur für den Zeit-Tail-Beweis bzw. reine Marker-Segmente).
Der Gesamt-Text wird suffix-getrimmt statt aus Segmenten neu zusammengesetzt
(identisches Ergebnis für die bisherigen Fälle, aber kein Umbau des
akkumulierten Streaming-Textes). Neu: Ein gemeinsamer Helfer
`_trim_marker_word_run` trimmt auch Wort-Timing-Listen (`words`) am Ende —
in der Pipeline (Segmente, die schon words tragen) UND in der Migration
(Bestands-Runs).

### 3. Regressionstests (test_transcript_marker.py)

- Chunked-Leak: Segment mit langem echtem Text + Marker-Suffix (Ratio < 0.5,
  Start weit vor Audio-Ende) → Marker weg, echter Text bleibt (rot vor Fix).
- Gemischtes kurzes Segment (ec98bfdf-Form, Ratio ≥ 0.5) → Abschied bleibt.
- Großschreibung/Interpunktion (`Seven, four, …`), Ziffern-, deutsche
  Variante, keine-Änderung-Fälle (< 4 Tokens, Phrase nicht am Ende).
- words-Listen: Marker-Wort-Einträge fallen, echte Wörter + deren Timings
  bleiben; kurze Läufe (< 4) unangetastet.
- Bestehende Tests (Zeit-Pop, reine Ziffern-Segmente ohne Zeitbasis) bleiben
  grün.

### 4. Datenmigration (prod, idempotent)

`webapp/scripts/ps185_marker_migration.py` (läuft im ps-webapp-Container,
nutzt dieselben Suffix-Trim-Helfer aus app.service): scannt
recording/transcriptionresult/transcriptversion, trimmt Text UND die letzten
Segmente inkl. deren `words`-Listen aller Zeilen mit Marker-Suffix.
Inhaltsscoped (nur found=True-Zeilen), kein Timestamp/Kein Versions-Snapshot,
Log je geänderter Zeile. Erwartung:
13 Zeilen (REC 318/322, TRES 133/149, VER 903–910/930) — lokal gegen einen
Real-Daten-Dump verifiziert (Text + words markerfrei, Segment-Timings
unangetastet, Abschieds-/Schluss-Sätze bleiben).

## Deploy

CI grün → KI-Box `./polyschnack-manage.sh pull && models && start`
(Overlays!) → Migration im neuen Container ausführen → Export der beiden
betroffenen Recordings gegenprüfen (Marker weg, Abschieds-Text bleibt).
