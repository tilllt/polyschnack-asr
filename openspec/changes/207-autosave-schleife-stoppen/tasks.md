# Aufgaben — Change 207

- [x] Befund aus dem Log gesichert: 1090 abgewiesene `PUT …/segments` für eine Aufnahme,
      Bursts bis 675 Anfragen in 7 s, **0 erfolgreiche** Speicherungen.
- [x] Betroffene Aufnahme geprüft: Segment in der Datenbank gesund, Stand vom Vortag —
      die Bearbeitung des Nutzers ist nie angekommen.
- [x] Ursache des Kreislaufs belegt: `save` hängt an `saving`, der Provider-Effekt an `save`
      → Neuaufbau der Verbindung pro Speicherversuch.
- [x] Leeren Stand als Auslöser der 400er identifiziert (Server lehnt leeren Text ab).
- [x] Hook: `savingRef`/`failuresRef` statt State in den Abhängigkeiten (stabile Identität).
- [x] Hook: leerer Stand wird nicht gesendet; `onSaveError` meldet einmal je Fehlerserie.
- [x] Hook: Backoff (vierfache Debounce-Zeit) nach einem Fehlversuch.
- [x] SegmentList: Hinweis in der Oberfläche statt stillem Schlucken.
- [x] Backend: Ablehnungsgrund wird protokolliert.
- [x] Sprachen: `collab_save_empty_text` (de/en/pt).
- [x] Tests: vier neue Hook-Tests; `tsc --noEmit` sauber; komplette Frontend-Suite 469 grün.
- [ ] CI, Deploy der Webapp, Gegenprobe im Log (keine 400-Bursts mehr, Speicherungen kommen an).
