# Change 141 — Design (Transkriptions-UI)

## 1. Zeilen-Umbruch via flex-wrap (minimal-invasiv)

Statt den JSX-Umbau (eigene Kopfzeile) wird die bestehende flex-Zeile auf
`flex-wrap` gestellt und Text/Textarea auf `w-full basis-full` — Timecode +
Sprecher bleiben in der ersten Zeile (items-baseline), der Text bricht
immer um und füllt die volle Breite. Keine Selektoren-Änderung (Tests
nutzen data-split-container), keine Struktur-Refactor-Risiken.

## 2. „Folgen"-Toggle

- SegmentList-Prop `followPlayback` (Default true): der Auto-Scroll-Effekt
  (activeWord-Zentrierung) bricht bei false ab — wie der bestehende
  Edit-Modus-Guard. Das Karaoke-Highlight (Wort-Färbung) ist unabhängig
  und bleibt aktiv (der User will nur das Scrollen abschalten).
- Toggle in der Transkriptions-Kopfzeile (bei Segmentlänge/Suche):
  aktiv = accent-gerahmt „Folgen", inaktiv = dezent. aria-pressed.
- Der Zustand ist pro Karte (RecordingCard-State), nicht global
  persistiert.

## 3. Suchfeld: type="text"

`type="search"` blendet in WebKit/Android ein NATIVES Such-Icon ein, das
zusätzlich zum eigenen Lucide-Icon über dem Placeholder liegt. `type="text"`
entfernt es; das eigene Icon (pl-[34px]) bleibt.

## 4. Start-Button

Send-Icon („los geht's", klar verschieden vom Play-Dreieck) + Outline
(border-accent, transparent, hover bg-accent/10) — dezent und optisch an
die Aktions-Tabs angebunden statt des gefüllten Akzent-Buttons.
