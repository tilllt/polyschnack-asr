# Change 203 — Design

## D1: Auswahlfeld statt Textfeld, aber offene Liste

Ein reines ``enum`` mit strenger Prüfung würde Skripten die Möglichkeit nehmen,
eine Schrift zu nennen, die hier nicht liegt (z. B. weil die Untertitel in einem
anderen Schnittprogramm weiterverwendet werden). Deshalb: ``type: enum`` mit
``open: true`` — die Oberfläche bekommt ein Dropdown, die API bleibt offen.
Die Längenbegrenzung (``max_len: 64``) und die Komma-Ersetzung gelten weiter,
weil die Style-Zeile der ASS-Datei komma-getrennt ist.

## D2: Werte aus der Wirklichkeit ableiten

Zwei Quellen:

* **messende Instanz** (Webapp-Image): ``fc-list : family`` — nur diese Schriften
  kann ``textfit`` messen, und die Messung bestimmt die Schriftgröße.
* **Renderdienst** (``/health``, neues Feld ``fonts``): nur diese Schriften kann
  libass beim Einbrennen auflösen.

Angeboten wird der Durchschnitt beider Mengen, dazu die drei Standardnamen, wenn
ihre Ersatzfamilie in beiden Mengen liegt (``Arial`` → ``Liberation Sans``,
``Times New Roman`` → ``Liberation Serif``, ``Courier New`` → ``Liberation Mono``).
Damit fällt z. B. ``Liberation Sans Narrow`` von selbst heraus: die Webapp hat es
(``fonts-liberation`` 1.07.4 unter bookworm), das Render-Image nicht (2.1.5 unter
trixie) — dort zeigt ``fc-match "Liberation Sans Narrow"`` auf ``Liberation Sans``.
Eine gepflegte Verbotsliste wäre hier falsch, weil sie beim nächsten Basiswechsel
still lügt.

Ist der Renderdienst nicht erreichbar oder meldet er (älteres Image) noch keine
Liste, bleibt die Liste der messenden Instanz. Das ist ehrlich: ohne Renderdienst
wird nichts eingebrannt, und die ASS-Datei misst die Webapp selbst.

## D3: Vorgabe immer im Auswahlfeld

``default`` ist ``Arial``. Steht der Standardname nicht in ``values``, zeigte ein
``<select>`` stumm den ersten Eintrag an, während der Wert weiter ``Arial``
wäre — genau die Art stiller Fehler, die wir nicht wollen. Der Standardname wird
deshalb notfalls ergänzt (dann greift fontconfigs Ersatzschrift, wie bisher).

## D4: Reihenfolge

Standardname und Ersatzfamilie als Paar, in der Reihenfolge ihrer Häufigkeit
(Sans, Serif, Mono); danach alle weiteren gefundenen Familien alphabetisch.
