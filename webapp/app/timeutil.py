"""Eindeutige UTC-Serialisierung für API-Zeitstempel (Change 081).

SQLite liefert naive UTC-Datetimes; naive ``.isoformat()``-Strings sind
mehrdeutig (Browser interpretieren sie als Lokalzeit → 2h-Skew in der
GUI, s. Change 081). ``iso_utc()`` serialisiert IMMER mit explizitem
``Z``-Suffix.
"""
from __future__ import annotations

from datetime import datetime, timezone


def iso_utc(dt: datetime | None) -> str | None:
    """Datetime als eindeutige UTC-Zeit serialisieren (…Z), nie mehrdeutig.

    - ``None`` → ``None``
    - naive UTC (SQLite) → ``…Z``
    - aware (beliebige Zone) → auf UTC normalisiert + ``Z``
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
