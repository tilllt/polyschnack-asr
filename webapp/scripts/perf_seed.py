"""Perf-Test-Seed: 90-min-Recording mit realistischer Segment-/Wort-Anzahl.

Erzeugt /tmp/perfdata/app.db mit einem fertigen Recording (status=done),
~2500 Segmenten und ~17.500 Wort-Spans (Karaoke) — plus share_token=True
für den /r/-Zugriff ohne Login. UID wird ausgegeben.

Nutzung: cd webapp && DATA_DIR=/tmp/perfdata .venv/bin/python scripts/perf_seed.py
"""
import random
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/data/pk-asr/webapp")

from sqlmodel import Session, SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Recording, User  # noqa: E402

random.seed(42)

WORDS = (
    "also", "dann", "aber", "und", "wir", "haben", "das", "gestern", "noch",
    "einmal", "besprochen", "der", "termin", "wurde", "auf", "nächste", "woche",
    "verschoben", "die", "frage", "ist", "ob", "wir", "das", "wirklich", "so",
    "machen", "können", "weil", "der", "aufwand", "deutlich", "größer", "wird",
    "als", "ursprünglich", "gedacht", "ich", "denke", "wir", "sollten", "erst",
    "die", "daten", "prüfen", "und", "dann", "entscheiden", "gut", "dann",
    "machen", "wir", "das", "so", "wie", "besprochen", "bitte", "alle",
    "unterlagen", "bis", "freitag", "zuschicken", "kein", "problem", "mache",
    "ich", "sofort", "danke", "dir", "sehr", "für", "die", "hilfe", "gerne",
)

DURATION_S = 5400.0          # 90 min
N_SEGMENTS = 2500            # ~2,16 s pro Segment
WORDS_PER_SEG = 7            # ~17.500 Wörter gesamt

def main() -> None:
    Path("/tmp/perfdata/audio").mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        if s.query(User).filter(User.kind == "oidc").first():
            print("DB existiert schon — seed übersprungen")
            return

        u = User(sub="perf-test-sub", kind="oidc", display_name="Perf Tester")
        s.add(u)
        s.flush()

        segments = []
        text_parts = []
        t = 0.0
        step = DURATION_S / N_SEGMENTS
        for i in range(N_SEGMENTS):
            start = round(t, 3)
            end = round(t + step, 3)
            t += step
            words = []
            seg_text = []
            wt = start
            for _ in range(WORDS_PER_SEG):
                w = random.choice(WORDS)
                dur = random.uniform(0.25, 0.45)
                words.append({"word": w, "start": round(wt, 3), "end": round(wt + dur, 3)})
                seg_text.append(w)
                wt += dur
            segments.append({
                "start": start, "end": end,
                "text": " ".join(seg_text),
                "speaker": random.choice(["A", "B"]),
                "words": words,
            })
            text_parts.append(" ".join(seg_text))

        rec = Recording(
            uid=secrets.token_hex(16),          # 32 chars
            original_name="perf-90min-test.m4a",
            title="Perf-Test 90 min",
            stored_path="/tmp/perfdata/audio/perf-90min-test.m4a",
            mime="audio/mp4",
            size_bytes=54_000_000,
            duration_s=DURATION_S,
            status="done",
            text=" ".join(text_parts),
            segments=segments,
            user_id=u.id,
            owner_user_id=u.id,
            share_token=True,
            shared_at=datetime.now(timezone.utc),
            processing_ms=int(DURATION_S * 1000 * 2.0),
            cost_cents=123,
            reserved_cents=None,
            language="de",
        )
        s.add(rec)
        s.commit()
        print(f"UID={rec.uid}")
        print(f"Segmente={len(segments)} Woerter={sum(len(x['words']) for x in segments)}")


if __name__ == "__main__":
    main()
