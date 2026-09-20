# Change 213 — Ein leeres Segment ist eine Löschung, kein Fehlerzustand

## Status
Entwurf (19.09.2026). Umsetzung nach dem laufenden Lauf (Regionsrahmen, Nutzungshinweise, Cache-Header).

## Nutzer-Befunde
1. „Beim laden der Seite wird dieser Toast jedesmal angezeigt: Not saved yet — one
   segment is empty. Add text and it saves automatically."
2. „Zum Verständnis wenn ein User alle Wörter aus einem Segment löscht, warum
   löscht sich das Segment dann nicht automatisch?"

## Ursache (belegt im Code)
`hooks/useYjsTranscription.ts:119` sucht das erste Segment ohne Text
(`!String(s.text ?? "").trim()`) und bricht dann **den gesamten Speichervorgang**
ab; Zeile 124 meldet die Ursache `empty_text`. `components/SegmentList.tsx:211`
macht daraus den Toast.

Zwei Folgen:
- **Die Warnung erscheint ohne Zutun des Nutzers.** Sie hängt am Laden des
  Dokuments, nicht an einer Bearbeitung.
- **Ein einziges leeres Segment blockiert das Speichern des ganzen Dokuments.**
  Änderungen an allen anderen Segmenten gehen verloren. Das ist ein
  Datenverlust-Risiko, versteckt hinter einer Hinweiszeile.

Es existiert kein Codepfad, der „Segment hat keinen Text mehr" als Löschung
deutet. Leere wird als verbotener Zustand behandelt, nicht als Absicht.

## Datenmodell (warum das die Ursache ist)
Ein Segment ist kein eigenständiges Objekt, sondern ein **Bereich über der
Wortliste**, und die Wortliste trägt die Zeiten (`recording.segments`). Wer den
Text eines Segments leert, entfernt damit den Inhalt, aber nicht die Wortzeiten.
Die Ableitung der Ansicht aus den Wortzeiten würde ein Wörter-Rest ohne Text
sofort wieder als leeres Segment zeigen.

## Entscheidung
**Leeren ist Löschen — auf beiden Ebenen.** Wird der Text eines Segments leer,
verschwindet das Segment **und** seine Wörter aus der Zeitliste (samt
Nachbarinvarianten: `start <= end`, kein Überlappen der Nachbarn).

Daraus folgt die Invariante **„kein Segment ohne Text"**. Sie ist danach
strukturell wahr und muss nicht mehr geprüft werden.

## Konsequenzen
1. Der Toast beim Laden entfällt — nicht durch Ausblenden, sondern weil sein
   Anlass nicht mehr entstehen kann.
2. Die Sammelblockade entfällt: ein leeres Segment kann das Speichern der übrigen
   Segmente nicht mehr verhindern.
3. Die Sichtbarkeit echter Speicherfehler bleibt (das war der Zweck von Change
   207 — ein fehlgeschlagener Autosave muss sichtbar sein).
4. Das Leeren per Löschtaste im Timing-Modus wird eindeutig definiert, statt in
   einer Sonderbehandlung zu landen.

## Aufgaben
1. Belegende Datenprüfung: Welches Segment ist in der betroffenen Aufnahme leer,
   und woher kommt es (Verarbeitung oder Bearbeitung)? Wenn es inhaltlich Text
   haben müsste, ist das ein zweiter Fehler und gehört in diesen Change.
2. Speicherpfad umbauen: leere Segmente werden als Löschung angewandt
   (Segmentbereich + zugehörige Wörter), statt den Vorgang abzubrechen.
3. Prüfung `leerIdx`/`empty_text` entfernen, sobald die Invariante strukturell
   gilt — kein Code, der einen unmöglichen Zustand überwacht.
4. Tests: Segment leeren → Segment und Wörter sind weg, Nachbarzeiten bleiben
   konsistent, übrige Segmente werden gespeichert.
5. Gegenprobe: Neue Aufnahme laden — kein Toast mehr.

## Offener Punkt
Zu klären ist, ob beim Löschen eines Segments die Grenzen der Nachbarn
nachgezogen werden (lückenlos) oder ob die Lücke bestehen bleibt. Vorschlag:
Lücke bleibt — sie entspricht der Realität der Aufnahme; ein Nachziehen wäre eine
stille Inhaltsänderung an Stellen, die der Nutzer nicht angefasst hat.
