# Change Proposal 007 — Segment-Edit-Fixes (Drag-Speichern, Karaoke-Stop)

**Status:** Proposed

## Why

Vier User-Befunde (2026-08-17) gegen die Transkriptions-GUI, nach
Reproduktionsrunde auf drei reproduzierte Root Causes zurückgeführt
(siehe `specs/transcription-view/spec.md`, „Bekannte Abweichungen"):

1. **Anzeige-Desync nach Grenz-Drag bei gesetztem `segMaxDuration`**
   (REPRODUZIERT): Drag verschiebt live korrekt, PUT speichert am Server
   korrekt (Reload zeigt die neue Grenze), aber die Anzeige springt nach
   dem Loslassen auf den alten Stand zurück. Root Cause: Reset-Effekt
   (`setDragSegments(cur => cur !== segments ? null : cur)`) vergleicht
   **Objekt-Referenzen**; `displaySegments` ist bei gesetztem
   `segMaxDuration` eine neu berechnete Liste → `cur !== segments` ist
   immer wahr → `dragSegments` wird auf `null` zurückgesetzt, obwohl
   `handleBoundaryDragEnd` gerade die Server-Liste gesetzt hat.
2. **Karaoke-Hervorhebung springt beim Stop** (REPRODUZIERT):
   `KARAOKE_LEAD_S=0.15` wird auch pausiert angewendet; zusätzlich
   übergibt `RecordingCard` `onPlayStateChange` nie → die App kennt den
   Play-Zustand nicht.
3. **Wort-Dopplungen / Timing-Bruch** (nicht in der puren Logik
   reproduzierbar): als Folge des Desyncs denkbar — User zieht, Anzeige
   springt zurück, zweiter Drag startet auf anderer Basis. Fix 1 beseitigt
   die vermutete Wurzel; erneuter Test danach.

Zusätzlich offener Pfad: **Drag während ein PUT noch offen ist (Race)** —
im GUI-Test nicht reproduziert (letzter Drag gewinnt), aber ungeschützt.

## What

### Fix 1 — Reset-Effekt auf Inhalts-Vergleich umstellen
`components/RecordingCard.tsx`:
- `useEffect` (`setDragSegments(cur => cur && cur !== segments ? null : cur)`)
  vergleicht nicht mehr Referenzen, sondern die **Wort-Invariante**:
  `flattenWords(cur) !== flattenWords(segments)`. Reset nur noch, wenn sich
  der Segment-Inhalt wirklich ändert (z. B. nach Retranscribe) — nicht bei
  PUT-Bestätigung derselben Liste.
- `handleBoundaryDragEnd`: Kommentar „result.segments ist referenz-gleich
  mit dem Cache" korrigieren (war die falsche Annahme des 16.08.-Fixes).

### Fix 2 — PUT-Guard „letzter Drag gewinnt"
`components/RecordingCard.tsx`:
- Monotone Drag-Sequenznummer (`useRef`): jeder `handleBoundaryDragEnd`
  inkrementiert; die Response wird nur übernommen, wenn ihre Sequenznummer
  noch aktuell ist (ältere PUT-Antworten verwerfen). Verhindert, dass eine
  langsame Antwort einen neueren Drag-Stand überschreibt.

### Fix 3 — Karaoke-Lead nur während des Playbacks
- `components/RecordingCard.tsx`: `onPlayStateChange` an `WaveformPlayer`
  durchreichen → `playing`-State in RecordingCard.
- `components/SegmentList.tsx`: `activeWordIndex(seg.words, currentTime)`
  mit `leadS = playing ? KARAOKE_LEAD_S : 0` aufrufen.
- `karaoke.ts`: Signatur/Default unverändert (Parameter existiert bereits).

## Changes

- Geändert: `components/RecordingCard.tsx` (Reset-Effekt, PUT-Guard,
  `onPlayStateChange`-Verdrahtung), `components/SegmentList.tsx`
  (Lead nur bei `playing`).
- Tests (neu, in `resegment.test.ts` / `karaoke.test.ts` / neuem
  `segment-edit.integration.test.ts`):
  - Inhalts-Vergleich: Drag-Liste mit identischem `flattenWords` wird
    NICHT zurückgesetzt; echte Neu-Inhalte schon.
  - PUT-Guard: zwei PUTs, ältere Antwort wird verworfen.
  - Karaoke: `activeWordIndex` mit `leadS=0` bei Stop-Zeit (bereits als
    REPRO-Test vorhanden) + Komponenten-Test für `onPlayStateChange`.
- GUI-Repro-Skripte (`/opt/data/perf-prof/repro_drag_*.mjs`) als
  Verifikation gegen Dev-Server nach dem Fix.

## Downgrade

- Fix 3: `leadS` wieder immer `KARAOKE_LEAD_S`, `onPlayStateChange`-Prop
  entfernen.
- Fix 2: Sequenznummer-Guard entfernen (zurück zu „jede Antwort gewinnt").
- Fix 1: Reset-Effekt zurück auf Referenz-Vergleich (alter Stand).
