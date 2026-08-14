"""WAL-Modus: Jede Engine-Verbindung aktiviert journal_mode=WAL + busy_timeout.

WAL entkoppelt Leser und Schreiber — parallele Streaming-Transkriptionen,
Uploads und Peaks-Schedules blockieren sich nicht mehr gegenseitig."""

from __future__ import annotations


def test_sqlite_pragmas_setzen_wal_und_busy_timeout():
    from app.db import _sqlite_pragmas

    calls: list[str] = []

    class FakeCur:
        def execute(self, sql: str) -> None:
            calls.append(sql)

        def close(self) -> None:
            pass

    class FakeConn:
        def cursor(self) -> FakeCur:
            return FakeCur()

    _sqlite_pragmas(FakeConn(), None)

    assert any("journal_mode=WAL" in c for c in calls), "WAL-PRAGMA fehlt"
    assert any("busy_timeout" in c for c in calls), "busy_timeout-PRAGMA fehlt"


def test_wal_ist_db_persistent(tmp_path):
    """journal_mode=WAL ist eine DB-Eigenschaft — nach dem Setzen bleibt sie."""
    import sqlite3

    db_file = tmp_path / "wal.db"
    con = sqlite3.connect(db_file)
    mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    con.close()

    # Nach erneutem Öffnen weiterhin WAL (kein erneutes Setzen nötig)
    con2 = sqlite3.connect(db_file)
    mode2 = con2.execute("PRAGMA journal_mode").fetchone()[0]
    con2.close()
    assert mode == "wal"
    assert mode2 == "wal"
