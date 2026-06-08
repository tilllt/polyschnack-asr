"""WhatsApp filename parser.

Pure helper — no I/O, no DB, no side-effects.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

# Matches (case-insensitive):
#   "WhatsApp Ptt 2026-05-26 at 13.45.08.ogg"
#   "WhatsApp Audio 2026-05-26 at 13.45.08 (1).ogg"
#   "WhatsApp-Ptt-2026-05-26-at-13.45.08.ogg"
#   Extra spaces / underscores between the tokens are tolerated.
_WA_RE = re.compile(
    r"whatsapp[\s_-]+(?:ptt|audio)\b"
    r".*?"
    r"(\d{4})-(\d{2})-(\d{2})"
    r"[\s_-]+at[\s_-]+"
    r"(\d{1,2})\.(\d{2})\.(\d{2})",
    re.IGNORECASE,
)


def parse_whatsapp(filename: str) -> tuple[Optional[dt.datetime], Optional[str]]:
    """Return *(recorded_at, source)* for a WhatsApp voice-note filename.

    If *filename* does not match the WhatsApp naming pattern, or the embedded
    date/time is not a valid calendar date, returns ``(None, None)``.

    Parameters
    ----------
    filename:
        The original filename as uploaded (basename only is fine; a full path
        also works because the regex is not anchored).

    Returns
    -------
    tuple
        ``(datetime, "whatsapp")`` on a successful match, ``(None, None)``
        otherwise.
    """
    m = _WA_RE.search(filename)
    if m is None:
        return None, None

    year, month, day, hour, minute, second = (int(x) for x in m.groups())
    try:
        recorded_at = dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.timezone.utc)
    except ValueError:
        # e.g. month=13, day=32 — not a real date
        return None, None

    return recorded_at, "whatsapp"
