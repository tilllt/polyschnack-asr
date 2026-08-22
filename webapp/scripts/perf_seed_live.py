"""Perf-Seed v2: LEBENDE Live-Daten (Box-JSON) in die lokale Perf-DB.

Nimmt /tmp/live_rec.json (curl auf die Share-API) und legt User + Recording
exakt so in /tmp/perfdata/app.db ab — für die eingeloggte Ansicht-Messung.
Nutzung: cd webapp && DATA_DIR=/tmp/perfdata .venv/bin/python scripts/perf_seed_live.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/data/pk-asr/webapp")

from sqlmodel import Session, SQLModel, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Recording, User  # noqa: E402

JSON_PATH = Path("/tmp/live_rec.json")

# JSON-API-Felder, die KEINE DB-Spalten sind (API-Derivate).
_SKIP = {
    "_words_debug", "access_level", "audio_missing", "audio_preview_url",
    "audio_url", "backup_url", "download_url", "eta_high_s", "eta_low_s",
    "eta_total_s", "has_shares", "is_anon_shared", "share_token",
    "shared_at", "shared_with_me",
}


def _coerce(key: str, val):
    if val is None:
        return None
    if key.endswith("_at") or key in ("created_at", "updated_at"):
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except ValueError:
            return None
    return val


def main() -> None:
    data = json.loads(JSON_PATH.read_text())
    SQLModel.metadata.create_all(engine)

    cols = set(Recording.__table__.columns.keys())
    fields = {k: _coerce(k, v) for k, v in data.items() if k in cols and k not in _SKIP}
    fields["stored_path"] = "/tmp/perfdata/audio/live-test.m4a"
    fields.pop("id", None)

    with Session(engine) as s:
        # Alten Seed (User + Recording) entfernen, damit die Liste eindeutig ist
        for rec in s.exec(select(Recording)).all():
            s.delete(rec)
        for u in s.exec(select(User)).all():
            s.delete(u)
        s.commit()

        u = User(sub="perf-test-sub", kind="oidc", display_name="Perf Tester")
        s.add(u)
        s.flush()
        fields["user_id"] = u.id
        fields["owner_user_id"] = u.id
        fields["share_token"] = False

        rec = Recording(**fields)
        s.add(rec)
        s.commit()
        print(f"UID={rec.uid}")
        print(f"name={rec.original_name} dur={rec.duration_s} segs={len(rec.segments or [])}")
        print(f"woerter={sum(len(x.get('words') or []) for x in (rec.segments or []))}")
        print(f"peaks={len(rec.waveform_peaks or []) if isinstance(rec.waveform_peaks, list) else 'n/a'}")


if __name__ == "__main__":
    main()
