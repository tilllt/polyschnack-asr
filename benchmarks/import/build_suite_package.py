#!/usr/bin/env python3
"""Build: 207er-Suite -> benchmark_data-Version (deterministisch) + package_sha256 + Tarball.

Quelle: /opt/data/polyschnack-benchmark/benchmark/data/manifest.json (aktive Suite,
von allen vast-Läufen verwendet). Ausgabe: benchmark_data/versions/vN mit
manifest.json (inkl. kanal/inhalt-Taxonomie) + audio/<id>.wav.

package_sha256 = sha256(sha256(manifest.json) || sha256(je WAV, alphabetisch))
— identische Formel wie BenchmarkService.package_sha256 (Change 036 Hash-Gate).
"""
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

SRC_MANIFEST = Path("/opt/data/polyschnack-benchmark/benchmark/data/manifest.json")
TAXONOMY = Path("/opt/data/polyschnack-benchmark/benchmark/spec/taxonomy.json")
OUT = Path("/opt/data/cache/benchmark_suite")
VERSION = int(os.environ.get("SUITE_VERSION", "2"))

def package_sha256(vdir: Path) -> str:
    mpath = vdir / "manifest.json"
    parts = [hashlib.sha256(mpath.read_bytes()).digest()]
    for wav in sorted((vdir / "audio").glob("*.wav")):
        parts.append(hashlib.sha256(wav.read_bytes()).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()

def main() -> int:
    m = json.loads(SRC_MANIFEST.read_text(encoding="utf-8"))
    samples = m["samples"]
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    mapping = tax.get("mapping_alt_neu", {})

    vdir = OUT / "versions" / f"v{VERSION}"
    audio_dir = vdir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    new_samples = []
    missing = []
    for s in samples:
        sid = s["id"]
        src = Path(s["audio_path"])
        if not src.exists():
            missing.append(sid)
            continue
        dest = audio_dir / f"{sid}.wav"
        if not dest.exists():
            dest.write_bytes(src.read_bytes())
        ziel = mapping.get(s["category"], {"kanal": "clean", "inhalt": "allgemein"})
        sample = {
            "id": sid,
            "category": s["category"],
            "kanal": ziel.get("kanal", "clean"),
            "inhalt": ziel.get("inhalt", "allgemein"),
            "text": s.get("text", ""),
            "source_path": s.get("source_path", ""),
            "accent": s.get("accent", ""),
            "age": s.get("age", ""),
            "quelle": s.get("quelle", ""),
            "held_out": s.get("held_out", False),
            "status": s.get("status", "active"),
        }
        new_samples.append(sample)

    if missing:
        print(f"WARN: {len(missing)} fehlende WAVs übersprungen: {missing[:5]}...")
    manifest = {
        "version": VERSION,
        "created_at": m.get("created_at"),
        "created_by": m.get("created_by", "benchmark-suite-build"),
        "supersedes": None,  # setzt das Box-Skript auf die aktive IST-Version
        "methodology": m.get("methodology"),
        "disclaimer": m.get("disclaimer"),
        "axes": m.get("axes"),
        "categories": m.get("categories", []),
        "samples": new_samples,
    }
    # Deterministisch serialisieren (sortierte Keys) -> reproduzierbarer Hash
    mpath = vdir / "manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sha = package_sha256(vdir)
    (OUT / "sha256.txt").write_text(sha + "\n", encoding="utf-8")
    print(f"Version v{VERSION}: {len(new_samples)} Samples, {len(list(audio_dir.glob('*.wav')))} WAVs")
    print(f"package_sha256: {sha}")

    # Deterministischer Tarball (mtime=0, keine UID/GID): Daten + SHA + Box-Skripte
    tgz = OUT / f"benchmark_suite_v{VERSION}_{sha[:8]}.tar.gz"
    rels = ["versions", "sha256.txt", "suite_import.py", "import_benchmark_suite.sh"]
    with tarfile.open(tgz, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for rel in rels:
            base = OUT / rel
            if not base.exists():
                continue
            files = sorted(base.rglob("*")) if base.is_dir() else [base]
            for f in files:
                if f.is_file():
                    ti = tar.gettarinfo(str(f), arcname=str(f.relative_to(OUT)))
                    ti.mtime = 0
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ""
                    with open(f, "rb") as fh:
                        tar.addfile(ti, fh)
    print(f"Tarball: {tgz} ({tgz.stat().st_size} Bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
