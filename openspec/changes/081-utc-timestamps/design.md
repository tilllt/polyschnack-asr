# Design — Change 081

## D1: Backend-Serialisierung zentral fixen (Root Cause)

Neues Modul `webapp/app/timeutil.py`:

```python
from datetime import datetime, timezone

def iso_utc(dt: datetime | None) -> str | None:
    """Datetime als EINDEUTIGE UTC-Zeit serialisieren (…Z), nie mehrdeutig."""
    if dt is None:
        return None
    if dt.tzinfo is None:          # SQLite liefert naive UTC
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
```

Alle 16 `.isoformat()`-Stellen in den 6 Routern
(account/annotations/keys/recordings/shares/versions) auf `iso_utc(...)`
umstellen; Import `from ..timeutil import iso_utc`.

Damit ist `new Date(iso)` im Frontend überall korrekt — der Offset
(`Z`) macht die Interpretation eindeutig. Bestandsdaten (naive Strings
in SQLite) werden beim Lesen korrekt als UTC ausgegeben.

## D2: Frontend-Defensive (zweite Verteidigungslinie)

`secondsSince()` (RecordingCard.tsx) und `fmtDate`/`fmtHHMM` (format.ts)
parsen naive Strings (kein `Z`/`±hh:mm` am Ende) explizit als UTC:

```ts
function parseUtcMs(iso: string): number {
  const hasOffset = /(Z|[+-]\d{2}:\d{2})$/.test(iso);
  return new Date(hasOffset ? iso : iso + "Z").getTime();
}
```

`secondsSince` bleibt die einzige Heartbeat-Quelle; `fmtDate`/`fmtHHMM`
konsistent, damit Zeitanzeigen nicht um 2 h wandern.

## D3: Tests

- Backend: Unit-Test `iso_utc` — naive UTC → `…Z`, aware → `…Z`
  (normalisiert), `None → None`.
- Frontend (`progress-heartbeat.test.ts`): naiver ISO-String → gleicher
  `secondsSince`-Wert wie mit explizitem `Z` (TZ-invariant).

## Offene Punkte

Keine.
