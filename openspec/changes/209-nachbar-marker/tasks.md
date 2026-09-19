# Aufgaben — Change 209

- [x] Nutzer-Vorgabe aufgenommen: Range-Marker für n-1/n+1, Mitschrumpfen, Nachbar anklickbar.
- [x] Bestand geprüft: Wort-Flow-Monotonie wurde serverseitig **hart abgelehnt** (400) und im
      Frontend an der Nachbar-Innenkante abgeklemmt — das musste weg.
- [x] Server: `shrink_neighbors` (opt-in) + `_neighbor_word_refs` + `_apply_shrink`; strenger Pfad
      unverändert; Log bei Verschiebung.
- [x] Server-Tests (9 neu) in `tests/test_word_timing.py` — inkl. Körper-Zug links/rechts und
      beide Kanten in einem Request; Datei 28 Tests grün.
- [x] Pur: `src/timingNeighbors.ts` (`neighborWords`, `shrinkNeighborEdges`) + 12 Tests.
- [x] `WaveformPlayer`: Nachbar-Marker (blass, mit Handles), Auswahl per Klick/Anfassen/Ziehen,
      Live-Folgen über `setOptions`.
- [x] `WaveformPlayer`: Nebenfund behoben — die aktive Markierung wandert beim Wortwechsel mit.
- [x] `RecordingCard`: Nachbar-State + Ausgangsstand-Ref, neue Zieh-Grenzen, Live-Schrumpfen, ein
      PATCH mit `shrink_neighbors`, Übernahme der Server-Antwort, Rollback inkl. Nachbarn.
- [x] `api.ts`: `shrink_neighbors` im Body-Typ.
- [x] Parent-Tests: Marker vorhanden, Live-Schrumpfen, Speichern, Nachbar anklicken (5 Tests).
- [x] `tsc --noEmit` sauber; volle Frontend-Suite grün.
- [ ] CI, Deploy, Gegenprobe am Gerät.
