# Change 163 — Versionen: Neustart vs. Diff erkennbar machen

**Status:** Proposed

## User-Anforderung (2026-08-30)

„Ein re-transcribe sollte einfach eine neue Version schreiben. In der
Versionsliste sollte auch erkennbar sein, welche Versionen ein diff zur
vorigen sind und welche 'Neustarts' — es macht keinen Sinn einen
re-transcribe als diff abzulegen."

## Befund (Recording 8976aa1b, Re-Transcribe Run 139 → V190)

- Backend legt beim Re-Transcribe bereits einen **Voll-Snapshot** an
  (`snapshot(..., "retranscribe")` — service.py, nach Run-Abschluss).
- Aber das Frontend zeigt beim Öffnen der Versionsliste sofort den **Diff
  der letzten gegen die vorletzte Version** (RecordingCard `loadVersions`)
  und bei Klick auf jede Version den **Diff gegen die Vorgängerin**
  (`showDiff` → `diff_endpoint` ohne `frm`).
- Bei einem Re-Transcribe ist die Vorgängerin eine komplett andere
  Transkription (anderer ASR-Lauf, andere Segmentierung, ggf. andere
  Sprache — Live-Beispiel: V189 deutsch → V190 mit ukrainischen Passagen).
  Der Diff zeigt dann nur „alles gelöscht + alles neu" — Rauschen, keine
  Information.

## Lösung

**Neustart-Kinds** (vollständige neue Basis, kein Diff zur Vorgängerin):
`transcribe`, `retranscribe`, `restore`. **Inkrementell** (Diff zur
vorigen sinnvoll): `edit`, `postprocess`.

1. **Backend `routers/versions.py` — `diff_endpoint`:**
   - Ohne explizites `frm`: Wenn `b.kind` ein Neustart-Kind ist →
     `{"from": None, "to": v_no, "diff": [], "restart": True}` (kein
     Auto-Diff gegen die Vorgängerin).
   - Mit explizitem `frm`: Diff weiterhin liefern (gezielter Vergleich
     bleibt möglich, z. B. „vorher/nachher" über einen Re-Transcribe).
2. **Backend `list_versions_endpoint`:** Jede Version bekommt ein Feld
   `restart: bool` (kind ∈ Neustart-Kinds), damit das Frontend die Liste
   ohne Raten kennzeichnen kann.
3. **Frontend `RecordingCard.tsx`:**
   - Versionsliste: Neustart-Versionen mit Badge „↻ Neustart" (statt
     Diff-Hinweis), Edits mit „✎ Diff zur vorigen".
   - `loadVersions()`: Auto-Diff nur laden, wenn die letzte Version KEIN
     Neustart ist (sonst bleibt der Diff-Bereich leer).
   - `showDiff(v)`: Bei Neustart-Kind keine Diff-Anfrage, sondern Hinweis
     „Vollständige neue Transkription (Neustart) — kein Diff zur vorigen".
4. **i18n:** neue Keys `version_restart`, `version_restart_hint` (de/en/pt).

## Tests

- Backend (`test_versions_api.py`): Neustart-Version ohne `frm` →
  `diff == []` und `restart == True`; mit `frm` → Diff vorhanden;
  edit-Version → Auto-Diff gegen Vorgängerin wie bisher.
- Backend: `list_versions_endpoint` liefert `restart`-Flag korrekt.
- Frontend: vorhandene RecordingCard-Tests bleiben grün (Mock-API).
