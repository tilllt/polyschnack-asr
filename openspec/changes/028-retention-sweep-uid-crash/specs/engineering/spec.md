# Engineering Spec — Delta für Change 028

## ADDED Requirements

### REQ-WEB-036: Health-Scan robust gegen uid-lose Legacy-Records
`Webapp` · `must`

`run_health_scan` darf nicht an Datensätzen mit `uid=None` scheitern:

- Das Logging der kaputten Records nutzt einen Fallback
  (`(uid or "?")[:8]`), kein `uid[:8]` direkt.
- Datensätze ohne uid werden weiterhin von `mark_broken` als
  `failed` markiert (unverändertes Verhalten).
- Ein Regressionstest deckt den Fall ab (Recording ohne uid,
  fehlende Datei → kein Exception, genau 1 Update).
