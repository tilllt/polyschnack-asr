"""PolySchnack Render-Dienst (Change 200).

Brennt animierte `.ass`-Untertitel in ein Video ein — oder erzeugt ein
Untertitel-Video **mit Alphakanal** (transparenter Hintergrund) zum
Drüberlegen im Schnittprogramm.

Bewusst klein und zustandslos: keine Datenbank, kein Zugriff auf Aufnahmen.
Der Dienst bekommt eine `.ass`-Datei und optional eine Video-/Audiodatei und
gibt eine fertige Datei zurück. Er ist damit wegwerfbar und kann jederzeit
fehlen (die Webapp arbeitet dann wie vor Change 200 weiter).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

VERSION = "1.0.0"

DATA_DIR = Path(os.environ.get("RENDER_DATA", "/data/render"))
JOB_TTL_S = int(os.environ.get("RENDER_TTL_S", str(24 * 3600)))
JOB_TIMEOUT_S = int(os.environ.get("RENDER_TIMEOUT_S", "1800"))
MAX_ASS_BYTES = 2 * 1024 * 1024
MAX_MEDIA_BYTES = 2 * 1024 * 1024 * 1024

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

# --------------------------------------------------------------------------
# Formate
# --------------------------------------------------------------------------
# Jedes Format nennt den Encoder, den es braucht. Fehlt der im Image, wird das
# Format gar nicht erst angeboten — so kann die GUI nichts anbieten, was
# hinterher scheitert.
FORMATS: Dict[str, dict] = {
    "burn_mp4": {
        "label": "MP4 (Untertitel eingebrannt)",
        "ext": "mp4",
        "mime": "video/mp4",
        "alpha": False,
        "encoder": "libx264",
        "note": "Fertiges Video. Ohne Videospur der Aufnahme wird ein "
                "einfarbiger Hintergrund erzeugt; liegt eine Audiodatei vor, "
                "wird deren Ton mitgenommen.",
    },
    "alpha_webm": {
        "label": "WebM (nur Untertitel, transparent)",
        "ext": "webm",
        "mime": "video/webm",
        "alpha": True,
        "encoder": "libvpx-vp9",
        "note": "Transparenter Hintergrund, kleine Datei. Zum Drüberlegen im "
                "Schnittprogramm oder im Browser.",
    },
    "alpha_mov": {
        "label": "MOV ProRes 4444 (nur Untertitel, transparent)",
        "ext": "mov",
        "mime": "video/quicktime",
        "alpha": True,
        "encoder": "prores_ks",
        "note": "Transparenter Hintergrund im Schnittprogramm-Standard. "
                "Deutlich größere Datei als WebM.",
    },
    "alpha_png": {
        "label": "PNG-Sequenz als ZIP (nur Untertitel, transparent)",
        "ext": "zip",
        "mime": "application/zip",
        "alpha": True,
        "encoder": "png",
        "note": "Universell, aber sehr groß. Für Programme ohne Alpha-Video.",
    },
}


def _ffmpeg_encoders() -> set:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    # Flags sind 6 Zeichen (z. B. "V....D", "A....D") — das D gehoert dazu.
    return {m.group(1) for m in re.finditer(r"^\s*[VAS][A-Z.]{5}\s+(\S+)", out, re.M)}


def _has_ass_filter() -> bool:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
    ).stdout
    return bool(re.search(r"\bass\b\s+V->V", out))


def _font_for(family: str) -> str:
    """Welche Schrift liefert fontconfig für diesen Namen? (Transparenz)"""
    try:
        out = subprocess.run(["fc-match", family], capture_output=True, text=True).stdout
        return out.strip().split(":")[0] or "?"
    except FileNotFoundError:
        return "fontconfig fehlt"


ENCODERS = _ffmpeg_encoders()
HAS_LIBASS = _has_ass_filter()


def available_formats() -> List[dict]:
    if not HAS_LIBASS:
        return []
    return [
        {"id": fid, **{k: v for k, v in spec.items() if k != "encoder"}}
        for fid, spec in FORMATS.items()
        if spec["encoder"] in ENCODERS
    ]


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
@dataclass
class Job:
    id: str
    format: str
    state: str = "queued"          # queued | running | done | failed | canceled
    progress: float = 0.0          # 0…1, aus ffmpeg -progress
    filename: str = ""
    size_bytes: int = 0
    error: str = ""
    created: float = field(default_factory=time.time)
    dir: Path = field(default_factory=Path)
    duration_s: float = 0.0
    _proc: Optional[subprocess.Popen] = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "format": self.format,
            "state": self.state,
            "progress": round(self.progress, 4),
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "error": self.error,
            "created_at": self.created,
        }


JOBS: Dict[str, Job] = {}
JOBS_LOCK = threading.Lock()
QUEUE: "queue.Queue[str]" = queue.Queue()
CURRENT: Dict[str, Optional[str]] = {"id": None}


def _clean_name(name: str, fallback: str) -> str:
    base = Path(name or fallback).name
    base = SAFE_NAME.sub("_", base).strip("._-") or fallback
    return base[:120]


def _dimensions(width: int, height: int) -> str:
    # gerade Zahlen: viele Encoder verlangen sie
    return f"{max(2, width // 2 * 2)}x{max(2, height // 2 * 2)}"


def build_ffmpeg_args(job: Job, ass_path: Path, media_path: Optional[Path],
                      width: int, height: int, fps: int, duration_s: float,
                      background: str, crf: int) -> List[str]:
    """Argumentliste für ffmpeg — kein Shell-String, keine Nutzereingabe im Befehl.

    Die Format-Beschreibung wird aus ``job.format`` geholt: ein zusätzlich
    übergebenes ``spec`` konnte zu einem anderen Format gehören als der Job
    (genau das hat ein Test aufgedeckt).
    """
    spec = FORMATS[job.format]
    size = _dimensions(width, height)
    out = job.dir / job.filename
    args = ["ffmpeg", "-hide_banner", "-nostats", "-y", "-progress", "pipe:1"]

    if spec["alpha"]:
        # Transparenter Untergrund: color mit Alpha 0, dann libass darüber.
        # `alpha=1` ist PFLICHT: ohne diese Option verwirft der ass-Filter den
        # Alphakanal und das Ergebnis ist deckend (gemessen: 0 % Transparenz).
        args += ["-f", "lavfi", "-i",
                 f"color=c=black@0.0:s={size}:r={fps}:d={duration_s:.3f},format=yuva420p"]
        filt = "ass=" + str(ass_path).replace("\\", "\\\\").replace(":", "\\:") + ":alpha=1"
    elif media_path is not None:
        args += ["-i", str(media_path)]
        filt = "ass=" + str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
    else:
        args += ["-f", "lavfi", "-i",
                 f"color=c=0x{background.lstrip('#')}:s={size}:r={fps}:d={duration_s:.3f}"]
        filt = "ass=" + str(ass_path).replace("\\", "\\\\").replace(":", "\\:")

    if job.format == "alpha_webm":
        args += ["-vf", filt, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                 "-auto-alt-ref", "0", "-b:v", "0", "-crf", str(crf),
                 "-metadata:s:v:0", "alpha_mode=1"]
    elif job.format == "alpha_mov":
        args += ["-vf", filt, "-c:v", "prores_ks", "-profile:v", "4444",
                 "-pix_fmt", "yuva444p10le", "-vendor", "apl0"]
    elif job.format == "alpha_png":
        # Sequenz: ffmpeg schreibt nummerierte Einzelbilder; das ZIP baut der
        # Job danach (ein einzelnes .zip kann ffmpeg nicht schreiben).
        args += ["-vf", filt, "-c:v", "png", "-pix_fmt", "rgba", "-f", "image2"]
    else:  # burn_mp4
        args += ["-vf", filt + ",format=yuv420p", "-c:v", "libx264",
                 "-preset", "veryfast", "-crf", str(crf), "-movflags", "+faststart"]
        if media_path is not None:
            args += ["-c:a", "aac", "-b:a", "160k"]

    if job.format == "alpha_png":
        args += ["-t", f"{duration_s:.3f}", str(job.dir / "frame_%05d.png")]
    else:
        args += ["-t", f"{duration_s:.3f}", str(out)]
    return args


def _zip_frames(job: Job) -> None:
    """PNG-Einzelbilder zu einem ZIP buendeln und die Bilder danach loeschen."""
    import zipfile

    frames = sorted(job.dir.glob("frame_*.png"))
    with zipfile.ZipFile(job.dir / job.filename, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in frames:
            zf.write(f, f.name)
    for f in frames:
        f.unlink(missing_ok=True)


def _run_job(job: Job, spec: dict, ass_path: Path, media_path: Optional[Path],
             width: int, height: int, fps: int, duration_s: float,
             background: str, crf: int) -> None:
    job.state = "running"
    log_path = job.dir / "ffmpeg.log"
    log = open(log_path, "wb")
    crashed = ""
    try:
        args = build_ffmpeg_args(job, ass_path, media_path, width, height,
                                 fps, duration_s, background, crf)
        (job.dir / "cmd.txt").write_text(" ".join(args), encoding="utf-8")
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log, text=True)
        job._proc = proc
        total_us = max(1.0, duration_s * 1_000_000)
        deadline = time.time() + JOB_TIMEOUT_S
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                if us >= 0:
                    # Fortschritt nur aus echten Zeiten — nie geschätzt.
                    job.progress = min(0.999, us / total_us)
            if time.time() > deadline:
                crashed = f"Zeitlimit ({JOB_TIMEOUT_S} s) überschritten"
                proc.kill()
                break
        rc = proc.wait()
        log.close()
        if crashed:
            job.state, job.error = "failed", crashed
        elif rc != 0:
            tail = log_path.read_text(errors="replace")[-1200:]
            job.state, job.error = "failed", f"ffmpeg endete mit {rc}: {tail}"
        elif job.state != "canceled":
            if job.format == "alpha_png":
                _zip_frames(job)
            out = job.dir / job.filename
            job.size_bytes = out.stat().st_size if out.exists() else 0
            if job.size_bytes == 0:
                job.state, job.error = "failed", "ffmpeg hat eine leere Datei erzeugt"
            else:
                job.progress = 1.0
                job.state = "done"
    except Exception as exc:  # pragma: no cover — Sicherheitsnetz
        job.state, job.error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        try:
            log.close()
        except Exception:
            pass
        job._proc = None
        _write_job_file(job)


# ---------------------------------------------------------------------------
# Wiederherstellung nach einem Neustart
# ---------------------------------------------------------------------------
# Der Dienst hielt seine Auftraege NUR im Arbeitsspeicher. Ein Neustart (Deploy,
# Absturz) machte damit fertige Dateien unauffindbar: der Nutzer bekam "Auftrag
# unbekannt" fuer ein Video, das vollstaendig auf der Platte lag (live passiert
# am 18.09., der Download brach dadurch ab).
#
# Beim Start wird deshalb rekonstruiert — und zwar nur, was nachweislich
# vollstaendig ist. Ein halbes Video darf nie ausgeliefert werden.

#: Dateien im Auftragsverzeichnis, die selbst keine Ausgabe sind.
_CONTROL_NAMES = {"cmd.txt", "ffmpeg.log", "meta.json", "job.json", "subtitles.ass"}


def _write_job_file(job: "Job") -> None:
    """Zustand sichern, damit ein Neustart den Auftrag wiederfindet."""
    try:
        (job.dir / "job.json").write_text(json.dumps({
            "id": job.id, "format": job.format, "state": job.state,
            "progress": job.progress, "filename": job.filename,
            "size_bytes": job.size_bytes, "error": job.error,
            "created_at": job.created, "duration_s": job.duration_s,
        }, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass          # kein Grund, den Auftrag deswegen scheitern zu lassen


def _media_duration_s(path: Path) -> Optional[float]:
    """Dauer laut ffprobe, oder None wenn die Datei nicht lesbar ist."""
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        value = float(res.stdout.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _completeness(path: Path, expected_s: float) -> tuple:
    """(vollstaendig?, Grund). Prueft Existenz, Lesbarkeit UND Laenge."""
    if not path.exists():
        return False, "Datei fehlt"
    if path.stat().st_size == 0:
        return False, "Datei ist leer"
    if path.suffix == ".zip":
        try:
            import zipfile
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if not names or zf.testzip() is not None:
                    return False, "Archiv ist unvollstaendig"
        except Exception:
            return False, "Archiv ist unvollstaendig"
        return True, ""
    duration = _media_duration_s(path)
    if duration is None:
        return False, "Datei ist nicht lesbar (unvollstaendig)"
    # Ein abgebrochener Lauf liefert eine kuerzere Datei — das ist der Fall,
    # den der Nutzer als "Download bricht ab" sieht.
    if expected_s > 1.0 and duration < expected_s - 1.5:
        return False, f"nur {duration:.1f} s von {expected_s:.1f} s gerechnet"
    return True, ""


def _recover_jobs() -> int:
    """Auftraege aus dem Datenverzeichnis zurueckholen (Rueckgabe: Anzahl)."""
    if not DATA_DIR.exists():
        return 0
    recovered = 0
    for job_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        saved, meta_path = job_dir / "job.json", job_dir / "meta.json"
        job: Optional[Job] = None
        if saved.exists():
            try:
                data = json.loads(saved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            job = Job(
                id=data.get("id") or job_dir.name,
                format=data.get("format") or "burn_mp4",
                state=data.get("state") or "failed",
                progress=float(data.get("progress") or 0.0),
                filename=data.get("filename") or "",
                size_bytes=int(data.get("size_bytes") or 0),
                error=data.get("error") or "",
                created=float(data.get("created_at") or 0.0) or job_dir.stat().st_mtime,
                dir=job_dir,
                duration_s=float(data.get("duration_s") or 0.0),
            )
        elif meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            fmt = meta.get("format") or ""
            if fmt not in FORMATS:
                continue
            media = (meta.get("media") or "").strip()
            candidates = [
                f for f in job_dir.iterdir()
                if f.is_file() and f.name not in _CONTROL_NAMES
                and not f.name.startswith("frame_") and f.name != media
            ]
            job = Job(id=job_dir.name, format=fmt, dir=job_dir,
                      created=job_dir.stat().st_mtime,
                      duration_s=float(meta.get("duration_s") or 0.0))
            if len(candidates) == 1:
                job.filename = candidates[0].name
                job.size_bytes = candidates[0].stat().st_size
                # Als "fertig" vormerken — die Vollstaendigkeitspruefung unten
                # stuft es wieder auf "failed" herunter, wenn etwas fehlt.
                job.state, job.progress = "done", 1.0
        if job is None:
            continue
        if job.state == "done":
            ok, why = _completeness(job_dir / job.filename, job.duration_s)
            if not ok:
                job.state = "failed"
                job.error = (f"Die Datei ist unvollstaendig ({why}) — der Dienst "
                             f"wurde waehrend des Auftrags neu gestartet. Bitte neu erzeugen.")
        elif job.state in {"running", "queued"}:
            job.state = "failed"
            job.error = ("Der Auftrag wurde durch einen Neustart des Dienstes "
                         "unterbrochen — bitte neu erzeugen.")
        with JOBS_LOCK:
            JOBS[job.id] = job
        _write_job_file(job)
        recovered += 1
    return recovered


def _worker() -> None:
    while True:
        job_id = QUEUE.get()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job is None:
            QUEUE.task_done()
            continue
        spec = FORMATS[job.format]
        meta = json.loads((job.dir / "meta.json").read_text(encoding="utf-8"))
        ass_path = job.dir / "subtitles.ass"
        media = job.dir / meta["media"] if meta.get("media") else None
        CURRENT["id"] = job_id
        try:
            _run_job(job, spec, ass_path, media, meta["width"], meta["height"],
                     meta["fps"], meta["duration_s"], meta["background"], meta["crf"])
        finally:
            CURRENT["id"] = None
            QUEUE.task_done()


def _cleanup_old() -> None:
    now = time.time()
    for path in DATA_DIR.glob("*"):
        try:
            if path.is_dir() and now - path.stat().st_mtime > JOB_TTL_S:
                shutil.rmtree(path, ignore_errors=True)
                with JOBS_LOCK:
                    JOBS.pop(path.name, None)
        except OSError:
            continue


def _cleanup_loop() -> None:
    while True:
        time.sleep(600)
        _cleanup_old()


app = FastAPI(title="PolySchnack Render", version=VERSION)


@app.on_event("startup")
def _startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old()
    # Fertige Dateien überleben den Neustart — sonst war ein Deploy der Grund,
    # dass ein bereits gerendertes Video nicht mehr herunterladbar war.
    wieder = _recover_jobs()
    print(f"recovery: {wieder} Auftrag/Auftraege aus dem Datenverzeichnis "
          f"wiederhergestellt (jeder wird beim Ausliefern auf Vollstaendigkeit geprueft)")
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_cleanup_loop, daemon=True).start()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if available_formats() else "degraded",
        "version": VERSION,
        "libass": HAS_LIBASS,
        "formats": available_formats(),
        "font_arial": _font_for("Arial"),
        "busy": CURRENT["id"] is not None,
        "jobs": len(JOBS),
        "ttl_s": JOB_TTL_S,
    }


@app.post("/render", status_code=202)
async def render(
    ass: UploadFile = File(...),
    format: str = Form(...),
    media: Optional[UploadFile] = File(None),
    width: int = Form(1920),
    height: int = Form(1080),
    fps: int = Form(25),
    duration_s: float = Form(...),
    background: str = Form("#101418"),
    crf: int = Form(28),
) -> JSONResponse:
    if format not in FORMATS or not any(f["id"] == format for f in available_formats()):
        raise HTTPException(status_code=400, detail={
            "error": "unsupported_format",
            "detail": f"Format '{format}' ist auf dieser Installation nicht verfügbar.",
        })
    if duration_s <= 0 or duration_s > 6 * 3600:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_duration", "detail": "Dauer muss zwischen 0 und 6 h liegen.",
        })

    job_id = uuid.uuid4().hex[:16]
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ass_bytes = await ass.read()
    if len(ass_bytes) > MAX_ASS_BYTES:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail={"error": "ass_too_large"})
    if b"[Script Info]" not in ass_bytes[:4096]:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail={
            "error": "invalid_ass", "detail": "Die Datei ist keine ASS-Untertiteldatei.",
        })
    (job_dir / "subtitles.ass").write_bytes(ass_bytes)

    media_name = ""
    if media is not None and format == "burn_mp4":
        media_name = _clean_name(media.filename or "media", "media.bin")
        written = 0
        with open(job_dir / media_name, "wb") as fh:
            while chunk := await media.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_MEDIA_BYTES:
                    fh.close()
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(status_code=413, detail={"error": "media_too_large"})
                fh.write(chunk)

    # Dateiname aus dem ASS-Namen ableiten. Endet der schon auf die Zielendung
    # (z. B. "folge.webm" -> WebM), nicht doppelt anhängen: sonst heißt der
    # Download "folge.webm.webm" (in der Live-Abnahme genau so passiert).
    base = _clean_name(Path(ass.filename or "untertitel").stem, "untertitel")
    ext = FORMATS[format]["ext"]
    filename = base if base.lower().endswith("." + ext) else f"{base}.{ext}"
    job = Job(id=job_id, format=format,
              filename=filename, dir=job_dir,
              duration_s=duration_s)
    (job_dir / "meta.json").write_text(json.dumps({
        "format": format, "media": media_name, "width": width, "height": height,
        "fps": fps, "duration_s": duration_s, "background": background, "crf": crf,
    }), encoding="utf-8")
    with JOBS_LOCK:
        JOBS[job_id] = job
    QUEUE.put(job_id)
    return JSONResponse(status_code=202, content=job.public())


def _get_job(job_id: str) -> Job:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        # Nach einem Neustart sind Jobs weg — ehrlich 404 statt Hänger.
        raise HTTPException(status_code=404, detail={
            "error": "unknown_job", "detail": "Auftrag unbekannt (oder Dienst neu gestartet).",
        })
    return job


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return _get_job(job_id).public()


@app.get("/jobs/{job_id}/file")
def job_file(job_id: str) -> FileResponse:
    job = _get_job(job_id)
    if job.state != "done":
        raise HTTPException(status_code=409, detail={
            "error": "not_finished", "detail": f"Auftrag ist im Zustand '{job.state}'.",
        })
    path = job.dir / job.filename
    if not path.exists():
        raise HTTPException(status_code=410, detail={
            "error": "expired", "detail": "Die Datei wurde bereits aufgeräumt.",
        })
    return FileResponse(path, media_type=FORMATS[job.format]["mime"],
                        filename=job.filename)


@app.delete("/jobs/{job_id}")
def job_cancel(job_id: str) -> dict:
    job = _get_job(job_id)
    if job.state in {"queued", "running"}:
        proc = job._proc
        if proc is not None:
            proc.kill()
        job.state = "canceled"
    return job.public()
