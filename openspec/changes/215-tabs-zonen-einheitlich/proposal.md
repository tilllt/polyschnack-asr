# Change 215 — Einheitliche Zonen in allen drei Tabs

## Status
Entwurf (20.09.2026), Nutzerauftrag. Umsetzung im selben Zug wie Change 212.

## Ausgangslage / Befund
Die drei Quellen-Tabs (Datei-Upload, Aufnahme, URL-Import) haben heute drei
verschiedene Zonen:

- **Upload:** eine Dropzone mit **gestrichelter** Linie, die zudem die
  größte Fläche im Fenster einnimmt.
- **Aufnahme:** keine Zone im eigentlichen Sinn — der Aufnahmeknopf steht frei
  im Raster, drumherum gibt es keine umschließende Fläche.
- **URL-Import:** ein Eingabefeld, ohne die Zone der beiden anderen.

Folge: Beim Umschalten springt die Anordnung, und dieselbe Sache sieht in jedem
Tab anders aus. Austauschbare Teile wirken wie verschiedene Bauteile.

## Nutzer-Vorgabe (20.09.2026, wörtlich)
„Bitte vereinheitliche in dem Zug auch das Design der Tabs. Die ‚Dropzone' vom
upload tab keine kleiner ca. 3/4 so gross. Passe das Design der ‚Zonen' aller
Tabs einheitlich aneinander an. Nicht bei Upload eine gestrichelten Linie, bei
recording nichts etc. Die area bleibt immer gleich gross."

## Entscheidung
1. **Eine Zone, ein Aussehen.** Alle drei Tabs benutzen dieselbe Klasse
   (`.ps-zone`) mit denselben Werten für Rand, Eckenradius, Hintergrund,
   Innenabstand und Ausrichtung. Der Unterschied liegt **nur** im Inhalt:
   Dateiauswahl, Aufnahmeknopf, Adresseingabe.
2. **Die gestrichelte Linie darf bleiben — solange die Maße gleich sind.**
   Nutzer-Klarstellung 20.09.2026: „Du kannst die gestrichelte Linie bei
   Dropzone auch beibehalten aber auf jedenfall sollte die area sich in der
   Größe nicht ändern." Also: Die **Geometrie** ist in allen drei Tabs
   identisch (Breite, Höhe, Eckenradius, Randstärke, Innenabstand). Die
   **Linienart** darf sich unterscheiden: gestrichelt im Upload als Hinweis
   „hier kann abgelegt werden", durchgezogen in den anderen Zonen. Randstärke
   und Radius bleiben trotzdem gleich, damit der Wechsel nicht sichtbar
   springt.
3. **Die Fläche ändert ihre Größe nie — innerhalb eines Breakpoints.**
   Nutzer-Ergänzung 20.09.2026: „Die fixe Größe der area muss sich allerdings den
   Screen Breakpoints anpassen und bei Desktop größer sein."

   Also: **drei feste Größen**, an einer Stelle als CSS-Variablen definiert und
   über Medienabfragen umgeschaltet — Mobil, ab 640 px, ab 1024 px. Innerhalb
   eines Breakpoints ändert sich die Fläche **nie**, auch nicht beim Inhaltswechsel
   oder beim Umschalten des Tabs; die drei Zonen eines Breakpoints sind exakt
   gleich groß. Zwischen den Breakpoints wird sie stufenweise größer, auf dem
   Desktop deutlich größer als auf dem Handy.

   Ausgangsgröße: Mobil rund **75 %** der heutigen Upload-Fläche; ab 640 px rund
   15 % mehr; ab 1024 px rund 40 % mehr. Die genauen Pixelwerte werden vor dem
   Umbau an der jetzigen Upload-Zone **gemessen**, nicht geschätzt.

   Kein Inhalt darf die Zone als Höhengeber benutzen: Hinweistexte, Dateilisten,
   Fortschrittszeilen und Fehlermeldungen liegen **innerhalb** der festen Fläche
   oder außerhalb der Zone.
4. **Die Aufnahme bekommt eine echte Zone.** Der Aufnahmeknopf steht mittig in
   dieser Zone, ihre Höhe richtet sich nach derselben Festlegung wie bei den
   anderen — nicht nach der Texthöhe der Hinweise.
5. **Lieber gemeinsam größer als verdichten (Change 217, Nutzer-Vorgabe
   20.09.2026).** Wörtlich: „Wenn der Platz in einem der Tabs nicht für alle UI
   Elemente reicht, mache alle tab-areas etwas größer."

   Regel daraus:
   - Reicht der Platz in **einem** Tab nicht für alle Bedienelemente, werden
     die drei Stufen **für alle Tabs gemeinsam** erhöht. Es gibt weiterhin nur
     **einen** Satz Stufen — nie eine Sonderhöhe für einen einzelnen Tab.
   - **Nicht verdichten und nicht abschneiden:** kein Element darf durch
     `overflow: hidden` verschwinden. Die Stufen sind so bemessen, dass jedes
     Bedienelement jedes Tabs vollständig sichtbar ist (in jedem Tab
     nachgemessen).
   - Die 75-%-Vorgabe für Mobil war der **Ausgangspunkt**, nicht die Obergrenze.
     Sie gilt nur so lange, wie dadurch keine Inhalte fehlen.
   - Bedienelemente eines Tabs liegen möglichst **innerhalb** der Zone. Passt
     eines dort nicht sauber hinein, kommt es in **eine** kompakte Zeile
     darunter — die Gesamthöhe des Tabs bleibt trotzdem in allen drei Tabs
     gleich.
   - **Kein Element doppelt:** derselbe Hinweis steht nicht gleichzeitig in der
     Hinweiszeile der Knopfkopie und in der Statuszeile.

   Umsetzung (Change 216/217, gemessen im Browser am 20.09.2026): Alle drei
   Tabs benutzen den gemeinsamen Rahmen `.ps-tab-body` mit fester Mindesthöhe
   („Zonenhöhe + 48 px"). Die neuen Stufen der Zonenhöhe:

   | Breite | vorher | jetzt | Fläche im Tab |
   | --- | --- | --- | --- |
   | bis 639 px | 124 px | **144 px** | 192 px |
   | ab 640 px | 143 px | **160 px** | 208 px |
   | ab 1024 px | 174 px | **174 px** | 222 px |

   Die Werte liegen weiterhin deutlich unter der ursprünglichen Upload-Fläche
   (165,67 px mobil, 189,67 px ab 640 px) und sind in allen drei Tabs gleich.

## Unverhandelbar (aus früheren Aufträgen)
- Der Aufnahmeknopf bleibt **mittig** und ändert seine Position nicht. Die
  Hinweise dazu liegen als halbtransparente Kopie in Knopfgröße **über** dem
  Knopf (eigener Auftrag, Change 212-Umfeld) — die Zone darf das nicht
  zunichte machen.
- Sprache Deutsch, keine Fachbegriffe ohne Erklärung, keine funktionslosen
  Knöpfe, keine stillen Fehler.
- Bei `prefers-reduced-motion` keine Bewegung.

## Prüfung (abzunehmen)
1. Die drei Zonen sind in Höhe und Breite messbar gleich (gleiche berechnete
   Werte, nicht „sieht ähnlich aus").
2. Die Höhe beträgt rund 75 % der bisherigen Upload-Fläche.
3. Rand und Eckenradius sind in allen drei Tabs identisch.
4. Der Aufnahmeknopf steht in der Zone mittig und bewegt sich bei
   Hinweiswechseln nicht.
5. Frontend-Typen fehlerfrei, Tests grün.
