# Change 141 — Tasks (Transkriptions-UI)

## 1. Zeilen-Layout

- [x] `SegmentList.tsx`: Zeile `flex-wrap`; Textarea + Text-Span
      `w-full basis-full` (Umbruch nach Sprecher, volle Breite)

## 2. „Folgen"-Toggle

- [x] `SegmentList.tsx`: Prop `followPlayback` (Default true) + Guard im
      Auto-Scroll-Effekt (Karaoke-Highlight bleibt aktiv)
- [x] `RecordingCard.tsx`: State + Toggle-Button (LocateFixed, aria-pressed)
      in der Transkriptions-Kopfzeile; Prop an SegmentList + TimingEditor
- [x] `TimingEditor.tsx`: Prop durchgereicht
- [x] i18n `follow_on/off/title` (de/en/pt-BR)

## 3. Suchfeld

- [x] `SearchBar.tsx`: `type="text"` statt `type="search"` (kein natives
      Such-Icon über dem Placeholder)

## 4. Start-Button

- [x] `RecordingCard.tsx`: `Send`-Icon statt `Play`, Outline-Stil (dezent,
      zu den Tabs gehörend)

## 5. Verifikation

- [x] tsc clean, 378 Vitest grün, build OK

## 6. OpenSpec + Commit

- [x] CLI-Validierung, Spec-Delta auf transcription-view, Archivierung
- [x] Commit, Push, CI-Watch, melden
