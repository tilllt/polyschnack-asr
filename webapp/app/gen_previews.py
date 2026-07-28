"""
One-shot backfill: generate _preview.mp3 for every existing recording that lacks one.

Run inside the container:
    python -m webapp.app.gen_previews
"""
from __future__ import annotations

import logging
import subprocess as sp
from pathlib import Path

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Recording

log = logging.getLogger(__name__)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with Session(engine) as session:
        rows = session.exec(select(Recording)).all()

    total = len(rows)
    ok = 0
    for i, rec in enumerate(rows, 1):
        wav_p = Path(rec.stored_path)
        if not wav_p.exists():
            log.warning("[%d/%d] %s: WAV file gone, skipping", i, total, rec.id)
            continue

        preview_p = wav_p.with_name(wav_p.stem + "_preview.mp3")
        if preview_p.exists():
            log.info("[%d/%d] %s: preview exists, skipping", i, total, rec.id)
            continue

        log.info("[%d/%d] %s: generating preview…", i, total, rec.id)
        try:
            sp.run([
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-i", str(wav_p),
                "-c:a", "libmp3lame", "-b:a", "64k",
                "-ar", "16000", "-ac", "1",
                str(preview_p),
            ], capture_output=True, timeout=120, check=True)
            if preview_p.exists() and preview_p.stat().st_size > 0:
                # Update DB row
                with Session(engine) as s:
                    r = s.get(Recording, rec.id)
                    if r:
                        r.preview_path = str(preview_p)
                        r.preview_size_bytes = preview_p.stat().st_size
                        s.add(r)
                        s.commit()
                ok += 1
                log.info("  ✅ %s → %s (%d bytes)", rec.id, preview_p.name, preview_p.stat().st_size)
            else:
                log.warning("  ⚠️ %s: ffmpeg produced empty file", rec.id)
        except sp.TimeoutExpired:
            log.warning("  ⏰ %s: ffmpeg timed out (120s)", rec.id)
        except sp.CalledProcessError as e:
            log.warning("  ❌ %s: ffmpeg failed: %s", rec.id, e.stderr.decode()[:200] if e.stderr else "?")

    log.info("Done. %d/%d previews generated.", ok, total)


if __name__ == "__main__":
    main()
