# Change 191 — Navigation: Top-Menü statt Admin-Sektion auf der Startseite

## Warum

Die Startseite trägt alles gleichzeitig: Upload, Queue, **Admin-Sektion**,
Suche, Aufnahmeliste. Wer nur transkribieren will, scrollt an Admin-Kacheln
vorbei (Guthaben, Tier, Vacuum, Schlüssel). Navigation gibt es faktisch nicht —
Benchmark hängt als loser Link neben dem Logo, Einstellungen hinter einem
⚙️-Knopf, Login/Logout als Textknöpfe. Der Blick findet keinen Anker.

## Was sich ändert

- **Top-Menü mit vier Einträgen:** Transkribieren (Default) · Settings ·
  Benchmark · Admin. Der aktive Eintrag ist hervorgehoben.
- **Admin-Sektion raus von der Startseite:** Sie zieht in die eigene Ansicht
  „Admin" (nur für `user.is_admin` sichtbar und nur dann gerendert).
- **Login/Logout als ein Symbol** neben dem Usernamen: nicht angemeldet →
  Anmelde-Symbol (führt zu `/auth/login`); angemeldet → Name + Abmelde-Symbol
  (führt zu `/auth/logout`). Die getrennten Textknöpfe „Login" und „Logout"
  entfallen.
- Der doppelte ⚙️-Knopf entfällt (Settings steht jetzt im Menü).

## Nicht Teil dieses Changes

Keine inhaltliche Änderung an Admin-, Settings- oder Benchmark-Funktionen —
nur ihre Verortung. `/benchmark` bleibt als eigener Pfad erreichbar (der
Menüpunkt schaltet dieselbe Ansicht).

## Auswirkung

Weniger Ballast auf der Arbeitsfläche (Transkribieren), klare Ortswechsel,
und niemand stolpert über Admin-Funktionen, der sie nicht nutzen darf.
