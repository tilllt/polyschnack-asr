"""Change 185: Test der Datenmigration gegen synthetische Kopie der
Prod-Belege (REC 318/322-Muster, Versionen, Nicht-Fälle, Idempotenz)."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/pk-asr/webapp")

spec = importlib.util.spec_from_file_location(
    "ps185", "/opt/data/pk-asr/webapp/scripts/ps185_marker_migration.py"
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

MARKER = "Seven, four, two, eight, one, six, zero, three, nine."


def _run(db_path: str):
    mod.DB = db_path
    return mod.main()


def test_migration_entfernt_marker_nur_wo_found(tmp_path: Path):
    db = tmp_path / "test.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE recording (id INTEGER PRIMARY KEY, text TEXT, segments TEXT);
        CREATE TABLE transcriptionresult (id INTEGER PRIMARY KEY, text TEXT, segments TEXT);
        CREATE TABLE transcriptversion (id INTEGER PRIMARY KEY, text TEXT, segments TEXT);
        """
    )
    # Prod-Muster 1 (ec98bfdf): kurzes gemischtes Segment — Abschied bleibt
    t1 = ("Gut, das waren die Fragen. Dann danke ich Ihnen. "
          "Okay. Dankeschön. Tschüss. " + MARKER)
    marker_words = [{"start": 410.0 + i, "end": 411.0 + i, "word": w}
                    for i, w in enumerate(
                        "Seven, four, two, eight, one, six, zero, three, nine.".split()
                    )]
    s1 = [
        {"start": 379.0, "end": 381.96, "text": "glaube ich schwierig"},
        {"start": 393.48, "end": 418.44,
         "text": "Okay. Dankeschön. Tschüss. " + MARKER,
         "words": ([{"start": 393.5, "end": 395.0, "word": "Okay."},
                    {"start": 395.5, "end": 397.0, "word": "Dankeschön."},
                    {"start": 397.5, "end": 399.0, "word": "Tschüss."}]
                   + marker_words)},
    ]
    # Prod-Muster 2 (941453a8): langes gemischtes Segment mit Marker-Suffix
    t2 = "Und an dem Punkt sind wir, glaube ich, nicht mehr. " + MARKER
    s2 = [{"start": 1575.6, "end": 1643.9, "text": t2}]
    # Nicht betroffen: normales Ende mit Zahl, leeres Text-Feld
    t3 = "Die Antwort ist 42."
    s3 = [{"start": 0, "end": 5.0, "text": "Die Antwort ist 42."}]
    cur = con.cursor()
    for t, s in [(t1, json.dumps(s1)), (t2, json.dumps(s2)),
                 (t3, json.dumps(s3)), (None, None)]:
        cur.execute("INSERT INTO recording (text, segments) VALUES (?, ?)", (t, s))
    cur.execute(
        "INSERT INTO transcriptionresult (text, segments) VALUES (?, ?)",
        (t1, json.dumps(s1)),
    )
    for _ in range(4):
        cur.execute(
            "INSERT INTO transcriptversion (text, segments) VALUES (?, ?)",
            (t2, json.dumps(s2)),
        )
    con.commit()
    con.close()

    rc = _run(str(db))
    assert rc == 0

    con = sqlite3.connect(db)
    cur = con.cursor()
    rows = cur.execute("SELECT id, text, segments FROM recording ORDER BY id").fetchall()
    expected = [
        "Gut, das waren die Fragen. Dann danke ich Ihnen. Okay. Dankeschön. Tschüss.",
        "Und an dem Punkt sind wir, glaube ich, nicht mehr.",
        "Die Antwort ist 42.",
        None,
    ]
    for (rid, text, _segs), exp in zip(rows, expected):
        assert text == exp, f"REC {rid}: {text!r} != {exp!r}"
    segs1 = json.loads(rows[0][2])
    assert segs1[-1]["text"] == "Okay. Dankeschön. Tschüss."
    assert segs1[-1]["start"] == 393.48  # Timing unangetastet
    w = segs1[-1]["words"]
    assert [x["word"] for x in w] == ["Okay.", "Dankeschön.", "Tschüss."]
    assert all("seven" not in x["word"].lower() for x in w)
    segs2 = json.loads(rows[1][2])
    assert segs2[-1]["text"].endswith("nicht mehr.")
    assert segs2[-1]["start"] == 1575.6
    tr = cur.execute("SELECT text FROM transcriptionresult").fetchone()
    assert tr[0] == expected[0]
    ver = cur.execute("SELECT COUNT(*), MAX(text) FROM transcriptversion").fetchone()
    assert ver[0] == 4 and ver[1] == expected[1], ver
    con.close()

    # Idempotenz: zweiter Lauf findet nichts mehr und ändert nichts
    rc2 = _run(str(db))
    assert rc2 == 0
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM recording WHERE text LIKE '%seven%'"
    ).fetchone()[0] == 0
    con.close()
