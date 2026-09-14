## ADDED Requirements

### Requirement: Angefragtes Music-Removal meldet Nichterfüllung

- **Ablauf:** Fordert ein Lauf Music-Removal an (`separate_backend` htdemucs /
  mel-band-roformer) und kann der Separations-Service nicht liefern (HTTP 409
  „Separation läuft bereits (ein Job gleichzeitig)", Service down, leere
  Vocals), läuft die Verarbeitung wie bisher auf dem Original-Audio weiter —
  aber die Nichterfüllung ist **sichtbar** (Job-Notiz + UI-Hinweis mit Grund),
  nicht nur im Server-Log.
- **Transparenz:** Der Hinweis nennt die angeforderte Separation und den Grund;
  das Ergebnis wird nicht als „mit Music-Removal" ausgewiesen.
- **Architektur:** `app/separate_client.py`, `app/service.py`
  (`_prepare_align_audio`, Align-Notiz), Frontend-Toast/i18n.

#### Scenario: Separation belegt (409)

- **Akteure:** Besitzer.
- **Eingaben:** Re-Align mit BGM-Entfernung starten, während ein anderer
  Separations-Job läuft.
- **Ergebnis:** Hinweis „Music-Removal nicht möglich (Separation läuft bereits) —
  auf Original alignt"; die Align-Ergebnisse werden trotzdem angewendet; kein
  stiller Rückfall.

#### Scenario: Separation erfolgreich

- **Akteure:** Besitzer.
- **Eingaben:** Re-Align mit BGM-Entfernung, Separations-Service frei.
- **Ergebnis:** Der Align läuft auf dem Vocals-Stem; der Job weist das
  Music-Removal als ausgeführt aus.
