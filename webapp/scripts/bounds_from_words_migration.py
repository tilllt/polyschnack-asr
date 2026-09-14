"""Change 187 — CLI: Segmentgrenzen aus den Wortlisten ableiten (Migration).

Im ps-webapp-Container ausführen (Image mit Change 187):
    python scripts/bounds_from_words_migration.py --dry          # Bericht
    python scripts/bounds_from_words_migration.py --dry --uid <uid>
    python scripts/bounds_from_words_migration.py --write        # schreiben

Schreiben nur mit explizitem --write (Default = Dry-Run). Text und Wortlisten
bleiben unverändert, je Recording entsteht ein Version-Snapshot (kind=edit).
Idempotent: ein zweiter Lauf findet nichts mehr.
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlmodel import Session

from app.bounds_migration import apply as apply_migration
from app.bounds_migration import plan as plan_migration
from app.db import engine, init_db


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Change 187: Grenzen aus Wörtern ableiten")
    ap.add_argument("--dry", action="store_true", help="nur Bericht (Default)")
    ap.add_argument("--write", action="store_true", help="Migration schreiben")
    ap.add_argument("--uid", default=None, help="nur dieses Recording (32-hex)")
    ap.add_argument("--limit", type=int, default=None, help="max. Recordings")
    args = ap.parse_args(argv)
    if args.dry and args.write:
        print("--dry und --write schließen sich aus", file=sys.stderr)
        return 2
    init_db()
    with Session(engine) as session:
        if args.write:
            report = apply_migration(session, uid=args.uid, limit=args.limit)
        else:
            report = plan_migration(session, uid=args.uid, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
