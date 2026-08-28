# Change 141: Transkriptions-UI — Layout, „Folgen"-Toggle, Suche, Start-Button

**Status:** Archived (auf specs/ angewendet, 2026-08-28)

## Problem (User-Befunde 2026-08-28)

1. **Zeilen-Layout:** Timecode und Sprechername rücken den Transkript-Text
   ein — der Text soll nach dem Sprecher umbrechen und die volle Breite
   des Containers ausfüllen.
2. **„Folgen"-Toggle fehlt:** Es gibt keinen Schalter, der das Auto-Scroll
   der Transkription an das Playback abschaltet — zum entspannten
   Lesen/Bearbeiten während das Audio läuft.
3. **Suchfeld:** Das Lupensymbol liegt über dem Placeholder „Search by
   name …" (das native WebKit-Such-Icon von `type="search"`).
4. **Start-Button:** Der gefüllte grüne Button mit Play-Icon wird mit dem
   Waveform-Play verwechselt — anderes Icon, dezenter, zu den Tabs
   gehörend.

## Ziel

- Segment-Zeile: Timecode + Sprecher in einer Zeile, danach Umbruch, der
  Text füllt die volle Breite.
- „Folgen"-Toggle (Default an): aus = kein Auto-Scroll, Karaoke-Highlight
  bleibt aktiv.
- Suchfeld ohne natives Such-Icon (eigenes Icon, kein Overlap).
- Start-Button mit Send-Icon, Outline-Stil, dezent.

## Changes

- `SegmentList.tsx`: Zeile `flex-wrap` + Text/Textarea `w-full basis-full`
  (Umbruch nach Sprecher); neue Prop `followPlayback` (Default true) —
  der Auto-Scroll-Effekt bricht bei false ab (Karaoke bleibt).
- `RecordingCard.tsx`: `followPlayback`-State + Toggle-Button
  (LocateFixed, „Folgen", aktiv/inaktiv-Stil) in der Transkriptions-
  Kopfzeile; Start-Button: `Send`-Icon + Outline (statt gefüllt + Play).
- `TimingEditor.tsx`: `followPlayback` durchgereicht.
- `SearchBar.tsx`: `type="text"` statt `type="search"` (kein natives
  Such-Icon mehr).
- i18n: `follow_on/off/title` (de/en/pt-BR).
- OpenSpec: Req-Delta transcription-view (Req 3/7).

## Downgrade

- Props/State entfernen, Zeile zurück auf `flex items-baseline`,
  `type="search"`, Start-Button mit Play-Icon.
