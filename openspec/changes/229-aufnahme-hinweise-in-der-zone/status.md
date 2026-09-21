# Change 229 — Aufnahme-Reiter: Hinweise in die Drop-Fläche, klickbasierte Texte

Nutzer-Auftrag 21.09.2026, wörtlich:

> Texte sind ok ABER: Aktuell sind die Texte ausserhalb der drop area. (Rec-Zeit-Zähler,
> input auswahl, UI Hints "Start Recording"). Ausserdem sind die Texte unklar:
> Click to Start recording (bei pause) und "click to stop recording", nicht swipe (bei recording)

## Befund (am lebenden System gemessen, REV eb081b84)

1. **Die Zeile stand außerhalb der Zone.** Aufnahmezeit, Mikrofon-Auswahl und der
   Bedienhinweis lagen in `.ps-tab-line` **unter** der Aufnahme-Zone. Die Zone selbst
   (`.ps-zone`, feste Höhe `--ps-zone-h`) enthielt nur Wellenform und Knopf.
2. **Der Hinweis bei laufender Aufnahme war eine Wisch-Anweisung.**
   `push_record_continuous` lautete „Daueraufnahme aktiv — nach unten wischen zum
   Stoppen". Dieser Text wird **nur auf Desktop** gezeigt: `statusText` liefert ihn
   genau dann, wenn `!isTouch` gilt — auf Touchgeräten wird er ausgeblendet. Die
   Wisch-Anweisung stand also ausgerechnet dort, wo es keine Wischgesten gibt.
3. **Die Wisch-Hinweise (`RecordGestureHint`) sind absichtlich Touch-only.**
   Gemessen: mit Touch-Emulation vorhanden (Kopie 66 × 66 px, Deckkraft 0,85,
   `ps-ghost-rise 1,9 s`, Zustand `running`), ohne Touch gar nicht im DOM
   (`navigator.maxTouchPoints = 0`). Grund steht im Code: der Desktop-Knopf ist ein
   reiner Klick, es gibt keine Geste vorzuführen.
4. Zweiter, unabhängiger Grund für „steht still": bei `prefers-reduced-motion: reduce`
   schaltet das CSS die Animation hart ab (`animation: none !important`) — ein
   Standbild, das die jeweilige Stellung zeigt (Barrierefreiheit, Change 218/223).

## Änderung

1. **Zeile in die Drop-Fläche.** Der Block (Aufnahmezeit, Bedienhinweis, Mikrofon-Auswahl)
   ist Kind der Aufnahme-Zone (`class="ps-tab-line ps-record-line"`) und per CSS
   (`.ps-zone > .ps-record-line`) **absolut am unteren Rand** verankert: `left/right: 0`,
   `bottom: 8px`. Damit gilt die Regel aus Change 215 unverändert — die Zone behält ihre
   feste Höhe und der Aufnahmeknopf bleibt exakt mittig (die Zeile ist nicht layoutwirksam).
2. **Klickbasierte Texte** (alle drei Sprachen):
   - Ruhe: `rec_btn` = „Aufnahme starten" / „Start Recording" / „Iniciar gravação" (unverändert).
   - Läuft: `push_record_continuous` = „Daueraufnahme aktiv — zum Stoppen klicken"
     / „Continuous recording — click to stop" / „Gravação contínua — clique para parar".
   - Pausiert: `push_record_paused` = „Pausiert — erneut drücken zum Fortsetzen" (unverändert,
     ist bereits eine Klick-Anweisung).
3. **Touch bleibt Touch:** die Wisch-Hinweise am Knopf werden weiterhin nur auf
   Touchgeräten gerendert — dort sind sie richtig. Auf Desktop trägt die Zeile in der
   Drop-Fläche die Klick-Anweisung.

## Belege

- `frontend/src/components/UploadZone.tsx` — Zeilenblock in der Zone, Hinweis-Renderer `{isTouch && …}`.
- `frontend/src/index.css` — `.ps-zone > .ps-record-line`.
- `frontend/src/useLocale.ts` — `push_record_continuous` in de/en/pt.
- Tor: tsc 0, 602 Frontend-Tests grün (51 Dateien), Bau durch.

## Offen

- Live-Messung nach dem Ausrollen: Zonenhöhe unverändert (192/208/212 px), Knopfmittigkeit,
  Zeile innerhalb der Zonengrenzen, Text bei laufender Aufnahme klickbasiert.
- Rückfrage an den Nutzer: soll die halbtransparente animierte Kopie zusätzlich auch auf
  Desktop erscheinen (dann ohne Wisch-Bewegung, nur mit Klick-Text)?
