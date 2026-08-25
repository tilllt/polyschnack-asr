# Change 129: Edit-Save trifft das richtige Server-Segment (Textverlust-Fix)

## Problem

Beim Bearbeiten einer Transkription sendet `handleSave` (SegmentList.tsx)
`PATCH /api/recordings/{uid}/segments/{idx}` mit dem **Anzeige-Index**.
Die Anzeige ist aber standardmäßig re-segmentiert (`deriveSegments` →
`resegmentByDuration`, Default 25 s): lange ASR-Segmente (bis ~83–119 s)
werden in mehrere Anzeige-Stücke geteilt. Ab dem ersten Split zeigen
Anzeige-Index und Server-Index nicht mehr auf dasselbe Segment.

**Real-Fall (2026-08-25, Teamtreffen):** Ein Edit um 14:04:41 traf das
falsche Server-Segment und überschrieb dessen Text mit einem stale/partiellen
Zustand — 541 Zeichen verloren, inklusive „…machen wir schonmal ein
Teammeeting, kann sein dass wir es morgen wiederholen…". Die ASR selbst war
korrekt (Run-Ergebnisse enthalten die Passage; alle ASR-Pfade entlastet).

Der Suchen/Ersetzen-Pfad wurde bereits auf `PUT /segments` (komplette
Anzeige-Liste, `segments_manual=True`) umgestellt — Kommentar:
„Server-Index-Problem entfällt". `handleSave` (normaler Edit) wurde nicht
umgestellt. Ein reiner PUT-Umstieg würde aber die Aufteilung nach dem
ersten Edit dauerhaft fixieren (`segments_manual=True` blockiert spätere
Segmentlängen-Wahl) — deshalb hier ein anderer Fix.

## Lösung

`handleSave` bildet den Anzeige-Index auf das **Server-Segment** ab:

1. `persistBase` (DB-Segmente, bereits als Prop vorhanden) ist die
   Server-Wahrheit.
2. Das editierte Anzeige-Stück wird zeitlich einem Server-Segment
   zugeordnet (`shown[idx].start ∈ [base[j].start, base[j].end)`).
3. Der neue Gesamttext des Server-Segments wird aus **allen**
   Anzeige-Stücken dieses Server-Segments rekonstruiert (das editierte
   mit dem neuen Text).
4. `updateSegment(recordingId, j, gesamtText)` — PATCH auf das richtige
   Segment mit dem vollständigen Text.

Wenn die Anzeige nicht aufgeteilt ist (keine Wörter / keine Splits), ist
`j == idx` und `gesamtText == editText` — Verhalten unverändert.

Nebenwirkung des Fixes: Auch der bekannte „Edit-Sync"-Effekt (UI zeigt
nach dem Edit den alten Text) verschwindet — Ursache war derselbe
falsche Index: die Server-Antwort änderte ein anderes Segment, das
editierte blieb in der Anzeige unverändert.

## Betroffene Dateien

- `webapp/frontend/src/components/SegmentList.tsx` (handleSave)
- `webapp/frontend/src/components/SegmentList.editindex.test.tsx` (neu)
