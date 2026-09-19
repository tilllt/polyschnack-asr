# Change 203 — Schriftauswahl als Auswahlliste

## Warum

Der Export-Dialog bot die Schriftart als **Textfeld** an (``font_name``, Typ
``str``). Wer den Namen nicht kennt, muss raten: Tippfehler und Namen, die
fontconfig gar nicht auflösen kann, fallen still auf die Ersatzschrift zurück —
der Export sieht dann anders aus als erwartet, ohne dass es jemand sagt.

Wunsch: eine Auswahlliste mit den Schriften, die dieser Server wirklich hat.

## Was sich ändert

1. ``font_name`` wird im Schema ein **Auswahlfeld** (``type: enum``); die GUI
   rendert daraus automatisch ein Dropdown (bestehende Mechanik, kein neuer
   Frontend-Pfad).
2. Die Auswahlwerte werden **abgeleitet, nicht gepflegt**: angeboten wird, was
   sowohl die messende Instanz (Webapp, ``fc-list``/``fc-match``) als auch der
   Renderdienst (``/health`` → neue Liste ``fonts``) **selbst** auflöst.
   Schriften, bei denen ein Host auf etwas anderes ausweicht, erscheinen nicht.
   Grund: die Schriftgröße wird in der Webapp gemessen, das Einbrennen
   passiert im Renderdienst — weichen beide ab, läuft der Text über den Rand.
3. Die Auflösung ist **offen** (``open: true``): die API nimmt weiterhin jeden
   wohlgeformten Namen an. Die Liste ist eine Hilfe in der Oberfläche, keine
   Sperre für Skripte.
4. Standardnamen zuerst: ``Arial``/``Times New Roman``/``Courier New`` (die
   metrik-gleichen Namen, die der Nutzer aus Schnittprogrammen kennt) jeweils
   gefolgt von der Familie, auf die sie hier abgebildet werden.

## Abgrenzung

* Kein neuer Parameter, keine Änderung an ``font_size`` oder am Layout.
* Kein Schrift-Download: es wird nur angeboten, was im Image liegt.
