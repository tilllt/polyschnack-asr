# Change 138 — Design-Entscheidungen (Bugfix-Runde)

## 1. Speaker-Rename: strikte Key-Funktion statt `_normalise_speaker`

`diarize._normalise_speaker` fällt bei unbekannten Werten auf `SPEAKER_00`
zurück — als MATCHING-Key ungeeignet (ein Segment ohne/leeres speaker würde
fälschlich als SPEAKER_00 matchen). Deshalb eine eigene, STRENGE Funktion:

```python
def _speaker_key(s: Any) -> Optional[int]:
    """Sprecher-Nummer extrahieren — oder None (kein Match).
    Versteht SPEAKER_01/SPEAKER_1/01/1/speaker_1/(speaker 0)/Buchstabe A-Z."""
    if s is None: return None
    t = str(s).strip().upper()
    m = re.search(r"(\d{1,2})", t)
    if m: return int(m.group(1))
    if t and "A" <= t[0] <= "Z": return ord(t[0]) - ord("A")
    return None
```

- `from_speaker`-Key und Segment-Key vergleichen → `s["speaker"] = to_speaker`.
- Mehrdeutigkeit: `SPEAKER_1` und `SPEAKER_01` sind DERSELBE Sprecher (Key 1).
  Ein (theoretischer) Fall, wo ein Segment `SPEAKER_01` und ein anderes
  `SPEAKER_1` trägt: beide werden umbenannt — gewollt (gleicher Sprecher).
- Buchstaben (A→0) nur als Fallback, falls ein Diar-Server Buchstaben-Labels
  liefert (CrispASR kennt das Format laut _normalise_speaker-Doku).
- `renamed`-Count zählt die tatsächlich ersetzten Segmente (ehrlich);
  400 nur, wenn NICHTS matcht (wie bisher).

## 2. Punctuation-Option: Backend-Capability in die UI

- Die Matrix liefert `native_punctuation` bereits (routers/models.py). Die
  RecordingCard baut daraus pro Backend eine Map (Muster `streamingByBackend`)
  und reicht `nativePunctuation` für das AKTUELL gewählte Backend an das
  OptionsPanel.
- Bei `native_punctuation=true`: Toggle disabled + optisch gesetzt, daneben
  ein „(nativ)"-Hinweis; der Erklärtext sagt ohne Fachbegriffe, dass der
  Server das automatisch macht. Kein stummer No-Op mehr.
- Default-Verhalten: Der Toggle-ZUSTAND (`enable_punctuation`) bleibt
  unverändert gespeichert — er steuert weiterhin nur den LLM-Fallback.
  Die Anzeige lügt nicht mehr darüber hinweg, was real passiert.

## 3. Detail-Poll bei queued: minimal-invasiv

- `enabled`: `!collapsed && (done | processing | queued)`.
- `refetchInterval`: `processing | queued → 2000`, sonst false.
- Warum nicht auch `uploaded`: nie transkribierte Aufnahmen sollen nicht
  dauerpollen (Cache/Netz). Der Transkribieren-Start setzt den Status auf
  `queued` → der Poll startet genau dann.
- Warum nicht den List-Poll ändern: Der Detail-Poll deckt den gemeldeten
  Fall (offene Karte) ab; der List-Poll bleibt schlank. Ein zusätzlicher
  List-Poll bei `queued` wäre überall aktiv (auch für Karten ohne offene
  Transkription).
- Reine Helfer `detailEnabled(status)` / `shouldPollDetail(status)` als
  Export für Unit-Tests (hooks.ts).

## Offene Punkte (nicht Teil dieses Changes)

- **Verlorene Aufnahme bei Abbruch:** Szenario unklar (abgebrochen vs.
  gestoppt+Upload-Fehler). Der IndexedDB-Schutz greift seit Commit 936813d
  bei `record-end`; ein Abbruch-Pfad (Blob auch bei Cancel sichern?) braucht
  die User-Entscheidung, ob abgebrochene Aufnahmen behalten werden sollen.
- **Text/Wort-Desync (Segment-Text vs. Aligner-Wörter, ec98bfdf…):**
  braucht die konkrete Recording + Box-Logs; wird separat verfolgt.
