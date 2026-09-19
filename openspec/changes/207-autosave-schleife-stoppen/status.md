# Status — Change 207

**Stand 19.09.2026:** Ursache belegt, Änderung umgesetzt, Tests grün. CI und Deploy stehen aus.

## Belege

- Log: 1090 × `PUT /api/recordings/4aed45f6…/segments` → 400, für **eine** Aufnahme,
  Bursts 675/194/178/245 Anfragen in je einer Sekunde; **keine** 200 für diese Aufnahme.
- Datenbank: Segment gesund (start 1,44 / end 14,88, 19 Wörter), `updated_at` vom Vortag
  → die Bearbeitung ist nie gespeichert worden.
- Log-Hinweis aus der Anwendung: „ohne Versionspruefung (Change 189) — Aufrufer sollte
  `expected_updated_at` mitschicken" → der Aufrufer ist der Yjs-Autosave (der einzige Pfad
  ohne diesen Parameter, der bei geteilten Aufnahmen läuft).
- Code: Provider-Effekt mit `save` in den Abhängigkeiten; `save` mit `saving` in den
  Abhängigkeiten → Neuaufbau pro Speicherversuch.

## Gegenprobe (noch offen, nach dem Deploy)

- Kein Burst mehr im Log; die nächste Bearbeitung einer geteilten Aufnahme landet in der
  Datenbank (`updated_at` wandert nach vorn).
- Bei einem abgelehnten oder fehlgeschlagenen Autosave erscheint ein Hinweis in der Oberfläche.
