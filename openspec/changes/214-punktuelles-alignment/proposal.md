# Change 214 — Punktuelles Alignment: nur markierte Wörter im gewählten Zeitbereich neu ausrichten

## Status
Entwurf (19.09.2026). Vor der Umsetzung steht die Prüfung der Align-Schnittstelle (Aufgabe 1) — davon hängt ab, ob es ein kleiner oder ein mittlerer Umbau wird.

## Anlass (Nutzerfrage, wörtlich)
„ist es möglich das wir eine dritte Funktion für unsere Markierungsfunktion
einbauen, nämlich ein punktuelles alignment was nur die markierten Wörter im
ausgewählten Zeitsegment neu markiert?"

## Ziel
Die Markierungsfunktion bekommt eine **dritte Aktion**: Sie richtet die
markierten Wörter innerhalb des markierten Zeitbereichs neu aus und lässt alles
außerhalb unangetastet.

Typischer Anwendungsfall: Ein Abschnitt ist im Timing abgedriftet — die Wörter
liegen sichtbar falsch, obwohl der Text stimmt. Heute hilft nur ein komplettes
Re-Alignment der ganzen Aufnahme; das ist teuer und verändert auch die Bereiche,
die in Ordnung sind.

## Ausgangslage
- Der Align-Dienst existiert als eigener Dienst im Stack und arbeitet auf Audio
  plus Text (Compose-Dienst `polyschnack-crispr-align-1`, in Produktion aktiv).
- Wortzeiten liegen in `recording.segments`; Segmente sind Bereiche über dieser
  Wortliste, keine eigenständigen Objekte.
- Die Markierungsfunktion kennt bereits zwei Aktionen (u. a. Split).
- Speicherungen legen Versionen an; Timing-Eingriffe sind damit rücknehmbar.

## Entwurf
1. **Ausschnitt statt Gesamtlauf.** Aus dem markierten Zeitbereich wird ein
   Audio-Ausschnitt erzeugt und mit **nur den markierten Wörtern** als Text an
   den Align-Dienst geschickt. Der Ausschnitt bekommt Vor- und Nachlauf
   (Vorschlag: 1–2 s), damit Anfang und Ende nicht ungenau werden; die
   zurückgegebenen Zeiten werden um den Vorlauf korrigiert.
2. **Nur der markierte Bereich wird zurückgeschrieben.** Wörter außerhalb der
   Auswahl behalten ihre Zeiten unverändert. Segmentgrenzen werden **nicht**
   angefasst — das entspricht der bestehenden Regel „Timing-Eingriffe verändern
   nie Segmente".
3. **Invarianten werden beim Zurückschreiben erzwungen:**
   - `start <= end` für jedes Wort,
   - kein Überlappen mit dem Wort davor,
   - `end` nicht hinter dem `start` des nächsten Worts,
   - das erste Wort des Bereichs beginnt nicht vor dem Bereichsbeginn, das
     letzte endet nicht nach dem Bereichsende (Toleranz bewusst festlegen).
4. **Zustände sichtbar machen.** Der Dienst kann scheitern oder nur teilweise
   treffen — besonders wenn der Text an dieser Stelle korrigiert wurde und nicht
   mehr eins zu eins zum Audio passt. Es gibt daher drei sichtbare Ergebnisse:
   gelungen, teilweise (mit Angabe, welche Wörter unsicher sind), kein
   Alignment. Kein stiller Teilerfolg (Nutzer-Regel: stille Fehler sind
   inakzeptabel).
5. **Bedienelement nur mit Auswahl.** Die Aktion ist gesperrt, solange nichts
   markiert ist — kein Knopf ohne Funktion.

## Sonderfall: Auswahl größer als 120 Sekunden (Nutzerfrage, 19.09.2026)
`MAX_ALIGN_GROUP_S = 120.0` ist die Sicherheitsmarge unter dem 400-s-Limit des
Modells (`app/service.py:1059`). Eine Auswahl über 120 s darf deshalb **nicht**
als ein Aufruf gehen, sonst arbeitet der Dienst außerhalb des Bereichs, für den
die Marge gilt. Verhalten:

1. Die Auswahl wird mit dem vorhandenen `build_align_groups(…)` in Abschnitte
   unter 120 s geteilt und **abschnittsweise** ausgerichtet (sequenziell, ein
   Aufruf je Abschnitt). Die Ergebnisse werden zusammengesetzt.
2. Die Abschnitte bekommen am Rand **Überlappung** (derselbe Vor-/Nachlauf wie
   Punkt 1). Ein Wort, das auf einer Abschnittsgrenze liegt, wird dem Abschnitt
   zugeordnet, in dem es mittiger liegt — sonst franst das Timing genau an den
   Nahtstellen aus.
3. Der Vorgang läuft als Hintergrundauftrag mit Fortschritt und Abbruch (beides
   existiert bereits). Der Fortschritt wird **echt** gemeldet (Abschnitt i von n),
   nicht geschätzt.
4. Obergrenze: Eine riesige Auswahl ist möglich, aber nicht sinnvoll, weil sie
   einem vollständigen Re-Alignment gleichkommt. Vorschlag: ab einer gewissen
   Länge (z. B. gesamte Aufnahme) den Hinweis, stattdessen das normale
   Re-Alignment zu nehmen — bedienbar bleibt es trotzdem.
5. **Noch offen und vor der Umsetzung zu prüfen:** Wie reagiert der Dienst selbst
   jenseits von 120 s / am 400-s-Limit — lehnt er ab, kürzt er, oder liefert er
   stillschweigend Unsinn? Solange das nicht belegt ist, gilt die Teilung als
   Pflicht, nicht als Optimierung.

## Aufgaben
1. **Schnittstelle geprüft (19.09.2026) — Ergebnis: punktuelles Alignment ist
   mit dem vorhandenen Aufbau möglich, der Umbau ist klein.**
   Belege aus dem Code:
   - `app/aligner_client.py:59` — `align(self, audio_bytes: bytes, text: str,
     lang: str = "de", …)`: Der Dienst nimmt **Audio-Bytes plus den zugehörigen
     Text** entgegen. Damit ist ein Ausschnitt mit einem Teilsatz ein regulärer
     Aufruf, kein Sonderfall.
   - `app/service.py:1059` — `MAX_ALIGN_GROUP_S = 120.0` mit
     `build_align_groups(segments, max_s)` (Zeile 1159) und den Gruppierungshelfern
     davor: Die Verarbeitung **gruppiert schon heute** in Abschnitte unter 120 s
     und richtet jede Gruppe einzeln aus (`client.align(chunk_bytes, g_text, …)`,
     Zeile 1361). Ein punktuelles Alignment ist damit genau **eine** solche
     Gruppe, gebildet aus dem markierten Bereich.
   - `app/service.py` — Hintergrundlauf und Abbruch existieren bereits
     (`_run_background_align`, `cancel_background_align`, `_BG_ALIGN_CANCEL`),
     inklusive Heartbeat-Poller gegen das lange Blockieren des Aufrufs.
   Also: kein neuer Dienst, keine neue Schnittstelle. Es fehlt die Auswahl-Steuerung
   (nur gewählte Wörter), das Ausschneiden mit Vor-/Nachlauf und das
   eingeschränkte Zurückschreiben.
   Noch zu prüfen (klein): ob der Dienst eine Mindestlänge des Ausschnitts
   verlangt und wie das Zurückschreiben heute die Invarianten behandelt.
2. Backend: Endpunkt für punktuelles Alignment (Zeitbereich + Wortliste →
   korrigierte Wortzeiten für genau diese Wörter), inklusive Ausschnitt-Erzeugung
   mit Vor-/Nachlauf und Invarianten-Erzwingung.
3. Frontend: dritte Aktion in der Markierungsfunktion, gesperrt ohne Auswahl,
   mit ehrlicher Rückmeldung (Fortschritt nur, wenn echt) und sichtbarem
   Ergebniszustand.
4. Tests: (a) Nachbarn außerhalb der Auswahl bleiben bitgenau unverändert,
   (b) Invarianten halten auch bei unplausiblen Aligner-Ergebnissen,
   (c) Fehlerfall erzeugt die Fehlermeldung statt eines stillen Nichts,
   (d) Version wird angelegt (Rücknahme möglich).
5. Doku: `docs/` ergänzen und die Aufnahme in den Change-Status aufnehmen.

## Abnahme
- Ein abgedrifteter Abschnitt lässt sich punktuell neu ausrichten, ohne dass
  Wortzeiten außerhalb der Auswahl sich ändern.
- Bei unpassendem Text erscheint ein klarer Zustand statt eines stillen
  Teilerfolgs.
- Die Aktion ist ohne Markierung nicht bedienbar.
- Über die Versionsliste ist der Eingriff rücknehmbar.

## Offene Fragen
1. Vor-/Nachlauf des Ausschnitts: 1 s oder 2 s? (Vorschlag 1,5 s.)
2. Toleranz an den Bereichsrändern: Dürfen die ersten/letzten Wörter leicht über
   die markierten Grenzen hinauslaufen, oder wird hart begrenzt?
   (Vorschlag: hart begrenzen, aber den Versuch sichtbar melden.)
3. Soll zusätzlich die Option bestehen, nach dem punktuellen Alignment die
   Segmentgrenzen an das neue Wort-Timing anzupassen? Vorschlag: nein — das
   widerspricht der bestehenden Regel und wäre eine zweite, getrennte Aktion.

## Messungen zum Verhalten über 120 s (19.09.2026)
**Vertrag (aus dem Code belegt, `app/aligner_client.py:59`):**
`align(audio_bytes, text, lang, method="qwen3", timeout_s=…)` postet an
`/v1/audio/align` und liefert `words` = `[{start, end, word}, …]` in Sekunden,
relativ zum Ausschnitt. Der Aufrufer verlässt sich darauf, dass **ein Wort je
Eingabewort** zurückkommt (`service.py`: „Change 187: per Wortindex zuordnen …
der Aligner liefert ein Wort je Eingabewort"), und `assign_words_by_index`
meldet eine Abweichung ausdrücklich als Fehler.

**Messung 1 und 2 — Zeitverhalten (gültige Teile):**
- 150 s in **einem** Aufruf: 21,5 s bzw. 22,2 s, Rückgabe vollständig.
- Dieselben 150 s in **zwei** Teilen à 76,5 s mit 1,5 s Überlappung:
  10,2 + 10,6 s bzw. 10,1 + 11,3 s, zusammen 20,8 / 21,4 s.
- Ergebnis: **Kein Zeitgewinn durch Teilen, und 150 s werden angenommen.**
  Die 120-s-Marge (`MAX_ALIGN_GROUP_S`) ist damit unsere Vorsichtsmaßnahme und
  keine vom Dienst durchgesetzte Grenze.

**Messung 2 — ungültig, ausdrücklich verworfen:**
Der Vergleich „ein Aufruf gegen zwei Teile" lieferte 444 zurückgegebene Wörter
bei 24 eingesandten (Teil 2: 259 bei 11). Das ist genau der Fehlerfall, den
`assign_words_by_index` kennt: **Der eingesandte Text passte nicht zum
Ausschnitt**, also hat der Dienst nicht zugeordnet, sondern frei erkannt. Damit
sind die Zahlen aus diesem Vergleich (mittlere Abweichung, Überlappungen) ohne
Aussage und werden nicht als Befund geführt.

Ursache der Text-Abweichung: Als Testmaterial wurde die dichteste Passage von
Aufnahme 335 gewählt — eine 4,4-h-Aufnahme mit nur 1 544 gespeicherten Wörtern.
Selbst ihr dichtestes 150-s-Fenster enthält nur 24 Wörter; gespeicherter
Transkript und Audiosprache passen dort offenbar nicht zusammen.

**Lehre für den Messaufbau (vor der nächsten Messung):**
Die Vorbedingung muss zuerst geprüft werden — erst einen kurzen Ausschnitt (etwa
30 s) senden und die **zurückgegebenen Wörter mit den gespeicherten vergleichen**.
Stimmen sie überein, ist das Material brauchbar; erst dann A/B über 150 s messen.
Ein Vergleich ohne bestandene Vorbedingung ist wertlos, egal wie sauber er rechnet.
