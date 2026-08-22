# Change 088 — Default-Re-Segmentierung der Transkriptions-Anzeige

**Status:** proposed → in Arbeit (2026-08-22)
**Problem:** ASR liefert chunk-bedingte Riesen-Segmente (95-min-Aufnahme =
48 Segmente, Ø 119 s, max 287 Wörter/Zeile). Die Segmentlängen-Wahl
(Feature 2026-08-15) existiert, hat aber KEINEN Default — ohne aktive
User-Eingabe zeigt die Anzeige die rohen Riesen-Blöcke (UX-Problem auf
Mobile, siehe Change 087).

## Lösung (User-OK 2026-08-22, Variante A — Anzeige-Default, Hybrid)

1. `segMaxDuration`-State in RecordingCard: Default **25 s** statt null
   (RecordingCard.tsx). Jede Aufnahme zeigt automatisch re-segmentierte
   Segmente ≤ 25 s (Sprecherwechsel trennt weiterhin).
2. **Hybrid statt Total-Stop:** Manuell angefasste Segmente bekommen bei
   jeder Bearbeitungs-OP (Grenz-Drag, +/−, Split) ein `_manual: true`-Flag
   (resegment.ts) — sie bleiben trotz Segmentlänge EXAKT erhalten. Nur
   unmarkierte Segmente (unangefasste ASR-Chunks) werden geteilt. Damit
   gilt der Default auch bei `segments_manual=true`: der angefasste Teil
   bleibt, der Rest („der größte Teil der Transkription") teilt sich.
3. Backend `resegment_by_duration` (service.py) respektiert `_manual`
   ebenso → Export (SRT/VTT) zeigt dieselbe Aufteilung wie die Anzeige.
   PUT /segments persistiert die Flags 1:1 (keine Feld-Whitelist).
4. User kann das Feld leeren → Original-Segmente (bisheriges Verhalten).

## Erwartete Wirkung

- 95-min-Aufnahme: 48 Riesen-Zeilen → ~136 Zeilen ≤ 25 s; ein manuell
  angefasstes 400-s-Segment bleibt als Ganzes (verifiziert: 120 Zeilen
  mit einem markierten 287-Wörter-Segment).
- Bestandsaufnahmen ohne Flags: alle Riesen-Chunks teilen sich (genau
  der Wunsch „Originale teilen sich").
- Alt-Logik „segments_manual stoppt alles" ist ersetzt — das Recording-
  Flag ist nur noch Metadatum, die Pro-Segment-Flags steuern.
