# caption-export — Änderung durch Change 203

## ADDED Requirement: Schriftauswahl als Auswahlliste

Der Export-Dialog MUSS die Schriftart als Auswahlliste anbieten (nicht als
freies Textfeld).

* Das Schema MUSS ``font_name`` als ``enum`` mit ``values`` liefern.
* ``values`` MUSS die Vorgabe (``default``) enthalten.
* ``values`` DARF nur Namen enthalten, die die messende Instanz UND der
  Renderdienst selbst auflösen; weicht ein Host auf eine andere Schrift aus,
  DARF der Name nicht angeboten werden.
* Die Auflösung ist offen: die Annahme eines wohlgeformten Namens außerhalb der
  Liste DARF NICHT abgelehnt werden (Skripte, fremde Schnittprogramme). Leere
  Namen, Überlänge und Kommas werden wie bisher behandelt.

#### Scenario: Dropdown statt Textfeld

* **GIVEN** die API liefert ``parameter_specs.font_name`` mit ``type: enum``
* **WHEN** der Export-Dialog das Feld rendert
* **THEN** erscheint eine Auswahlliste mit genau diesen Werten

#### Scenario: Schrift nur auf einem Host

* **GIVEN** die messende Instanz kennt ``Liberation Sans Narrow``, der
  Renderdienst löst denselben Namen auf ``Liberation Sans`` auf
* **WHEN** die Auswahlwerte gebildet werden
* **THEN** enthält ``values`` weder ``Liberation Sans Narrow`` noch einen
  anderen Namen, der auf einem Host anders auflöst

#### Scenario: Renderdienst nicht erreichbar

* **GIVEN** ``/health`` liefert keine Fontliste
* **WHEN** die Auswahlwerte gebildet werden
* **THEN** stammen sie aus der messenden Instanz, und die Vorgabe ist enthalten
