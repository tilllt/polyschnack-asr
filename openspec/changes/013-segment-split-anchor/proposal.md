# Change Proposal 013 — Split-Symbol statt Auto-Modal + Timing-Klärung

**Status:** Proposed

## Why

Drei User-Befunde (2026-08-17) zur Transkriptions-GUI:

1. **Das automatische Split-Modal nach Text-Markierung funktioniert UX-mäßig
   nicht.** `SegmentList.handleTextMouseUp` öffnet bei JEDER Text-Markierung
   sofort ein zentriertes Modal (Sprecherwahl + Bestätigen). Der Dialog
   erscheint mitten im Bildschirm, weg vom Markierungskontext; er unterbricht
   den Lese-/Edit-Fluss. Gewünscht (User): Die GUI erkennt eine Markierung
   und blendet **links am Rand, auf der Höhe des Markierungsbeginns**, ein
   Split-Symbol ein (horizontal-split-Icon). Erst der Klick darauf führt den
   Split aus.
2. **Doppelklick für Edit funktioniert auf Desktop nicht.** Der Doppelklick
   markiert (Browser-Wort-Selektion) → `mouseup` → Split-Modal öffnet sich
   und überlagert den Edit-Modus. Root Cause ist identisch mit Punkt 1 —
   das Auto-Modal unterbricht. Erwartung: Mit Punkt 1 (Symbol statt Modal)
   funktioniert der Doppelklick-Edit automatisch wieder.
3. **Timing zwischen Audio und Wort-Hervorhebung geht nach Grenz-Verschiebung
   „verloren".** Analyse (s. u.): Die Datenebene ist sauber — `moveBoundary`
   und der Server kopieren Wort-Timestamps exakt (Req-10-Invariante,
   `flattenWords`-Tests grün). Das beobachtete Symptom ist der bekannte
   **Aligner-0-Dauer-Bug** (`end[i] = start[i+1]` bei 98 % der Wörter,
   Stille gehört Wörtern): Die Wort-Timestamps sind VOR dem Verschieben
   schon falsch; der Grenz-Drag macht es nur sichtbar (Grenzen liegen dann
   nicht mehr zufällig auf den falschen Wort-Enden). Kein Code-Fix in
   dieser Change — Fix ist der Aligner-Energie-Korrektur-Deploy
   (`1a9f79f`, CI grün, wartet auf Deploy).

## What

### 1. Split-Anker statt Auto-Modal (Punkt 1 + 2)

`handleTextMouseUp` öffnet kein Modal mehr. Stattdessen:

- Bei gültiger Text-Markierung (nicht volle Segment-Selektion, nicht beim
  Editieren) wird ein **Anker-State** gesetzt: `{idx, charStart, charEnd,
  preview}` + die **Y-Position** des Markierungsbeginns relativ zur
  Segment-Zeile (via `Range.getBoundingClientRect()`).
- Die Zeile rendert links am Rand (im linken Button-Kanal, neben − / vor
  dem Timecode) ein **Split-Symbol** auf genau dieser Höhe (absolut
  positioniert, `left`-Kanal). Icon: eigenes Inline-SVG im Stil der
  horizontal-split-Idee (kein Flaticon-Asset — Lizenz/Attribution; SVG
  passt sich der `accent`-Farbe an).
- Klick auf das Symbol → das bisherige Bestätigungs-Popover (Sprecherwahl
  + „Teilen") erscheint — jetzt als **bewusste Aktion**, kontextnah.
- Markierung entfernen/Klick weg → Anker verschwindet.
- **Doppelklick-Edit:** Mit dem Auto-Modal entfällt der Unterbruch. Der
  Doppelklick setzt `editingIdx`; während des Editierens ist der Split-Anker
  ohnehin deaktiviert (`editingIdx !== null`-Guard in `handleTextMouseUp`
  existiert bereits). Verifikation im Browser-Test.

### 2. Timing (Punkt 3) — Dokumentation, kein Code

- Kein Frontend-/Backend-Code. Die Req-10-Invariante ist bereits durch
  `flattenWords`-Tests abgesichert; die Beobachtung ist Folge des
  Aligner-0-Dauer-Bugs (Stille gehört Wörtern), behoben durch den
  Energie-Fix im Aligner-Service (`1a9f79f`), Deployment ausstehend.
- Nach dem Deploy: Karaoke-Zeiten gegen die Audio-Position prüfen
  (Wortgrenzen müssen mit hörbaren Silben übereinstimmen).

## Changes

- **Geändert:** `webapp/frontend/src/components/SegmentList.tsx` —
  `handleTextMouseUp` setzt Anker statt Modal; Split-Symbol (Inline-SVG,
  absolut links auf Markierungshöhe); Klick → bestehendes
  Bestätigungs-Popover (kontextnah statt zentriert); Anker-Clearing.
- **Geändert:** `webapp/frontend/src/components/SegmentList.tsx` —
  `selectionCharRange` unverändert; neu: Hilfsfunktion für die
  Markierungs-Y-Position.
- **Tablet (Bonus-Frage 2026-08-17):** Google-Suchassistent-Popup bei
  Wort-Markierung verhindern. Kein API unterdrückt das Popup gezielt —
  es hängt an der NATIVEN Selection-UI. Lösung: auf Touch-Geräten
  (`pointer: coarse`) `user-select: none` + `-webkit-touch-callout: none`
  auf dem Segment-Text; die Markierung wird stattdessen EIGENES erkannt
  und visualisiert (Pointer-Events → Wort-Range → CSS-Highlight auf den
  Wort-Spans). Desktop (Maus) behält die native Selektion (kein Popup,
  `selectionCharRange` unverändert). Doppelklick-Edit profitiert
  zusätzlich: native Wort-Selektion kann den Edit nicht mehr unterbrechen.
- **Tests (vitest):**
  - Anker wird bei Markierung gesetzt (nicht bei voller Segment-Selektion,
    nicht beim Editieren).
  - Klick auf das Symbol löst `onSplitSegment` mit korrektem
    Range/Speaker aus (Logik unverändert, nur Einstieg geändert).
  - Bestehende Split-Unit-Tests (`resegment.test.ts`) bleiben grün —
    `splitSegmentAtRange` wird nicht angefasst.
- **GUI-Test (Playwright, `/opt/data/perf-prof/`):** Markierung → Symbol
  links auf Markierungshöhe sichtbar (kein Modal); Klick → Popover;
  Doppelklick → Edit-Modus ohne Modal-Unterbruch.
- **OpenSpec:** Req-5-Delta (Split-UI) in `transcription-view` (s. Spec).

## Alternativen verworfen

- **Flaticon-Asset einbinden:** vermeidet Lizenz-/Attributionspflicht;
  eigenes SVG ist an die UI-Farben anpassbar und ~200 Bytes.
- **Split per Kontextmenü:** auf Desktop zusätzliche Klick-Zahl; das
  Symbol ist ein Klick wie das bisherige Modal.
