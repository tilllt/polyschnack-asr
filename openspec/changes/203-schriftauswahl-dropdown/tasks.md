# Change 203 — Aufgaben

## Renderdienst

- [x] ``/health`` um ``fonts`` erweitern (Familien aus ``fc-list``, sortiert).
- [x] Test: ``fonts`` ist eine Liste; enthält ``Liberation Sans``.

## Webapp

- [x] ``textfit.font_families()`` — Familien der messenden Instanz, gecacht.
- [x] ``presets.font_choices(eigene, fremde)`` — reine Auswahllogik (testbar ohne
      fontconfig), inkl. Standardnamen-Paare und Vorgabe-Garantie.
- [x] ``font_name`` auf ``enum`` + ``open`` umstellen; ``_coerce`` offene
      Auswahl wie ``str`` behandeln (Länge, Komma).
- [x] ``parameter_specs(render_families=…)`` füllt die Auswahlwerte;
      ``/api/export/presets`` reicht die Fontliste aus der Health-Antwort durch.
- [x] Tests: ``tests/test_export_fontwahl.py`` + Frontend (Dropdown statt Textfeld).

## Doku

- [x] ``docs/caption-export.md``: Schriftauswahl, Herkunft der Liste, offene API.
