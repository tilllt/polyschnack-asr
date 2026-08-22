"""Change 081: iso_utc — eindeutige UTC-Serialisierung von Zeitstempeln."""
from datetime import datetime, timedelta, timezone

from app.timeutil import iso_utc


def test_naive_utc_gets_z_suffix():
    dt = datetime(2026, 8, 22, 11, 48, 59, 589231)
    assert iso_utc(dt) == "2026-08-22T11:48:59.589231Z"


def test_aware_utc_gets_z_suffix():
    dt = datetime(2026, 8, 22, 11, 48, 59, tzinfo=timezone.utc)
    assert iso_utc(dt) == "2026-08-22T11:48:59Z"


def test_aware_other_tz_normalized_to_utc():
    dt = datetime(2026, 8, 22, 13, 48, 59, tzinfo=timezone(timedelta(hours=2)))
    assert iso_utc(dt) == "2026-08-22T11:48:59Z"


def test_none_returns_none():
    assert iso_utc(None) is None


def test_no_more_naive_isoformat_in_routers():
    """Kein Router darf Zeitstempel mehr OHNE Zeitzonen-Suffix ausliefern."""
    import pathlib

    import app.routers as routers

    base = pathlib.Path(routers.__file__).parent
    offenders = []
    for py in base.glob("*.py"):
        for line_no, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if ".isoformat()" in stripped and not stripped.startswith(("#", '"""', "'''")):
                # iso_utc(...) intern darf isoformat enthalten — nur direkte Aufrufe meiden
                if "iso_utc(" not in stripped or ".isoformat()" in stripped.split("iso_utc(")[0]:
                    offenders.append(f"{py.name}:{line_no}")
    assert offenders == [], f"naive .isoformat() in: {offenders}"
