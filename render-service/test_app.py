"""Tests für den Render-Dienst (Change 200).

Der Kern ist der Alpha-Nachweis: für die Transparenz-Formate wird das Ergebnis
dekodiert und **pixelweise** geprüft — transparent, wo kein Text ist, und
deckend, wo Text steht. Ein „läuft ohne Fehler" reicht hier nicht: ffmpeg
meldet auch dann Erfolg, wenn der Alphakanal unterwegs verloren geht.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("RENDER_DATA", "/tmp/render-service-test")

import app as render_app  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,160,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,2,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hallo Welt
"""


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["RENDER_DATA"] = str(tmp_path_factory.mktemp("render"))
    render_app.DATA_DIR = Path(os.environ["RENDER_DATA"])
    render_app.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(render_app.app) as c:
        yield c


def run_job(client, fmt: str, **form) -> dict:
    files = {"ass": ("untertitel.ass", ASS.encode("utf-8"), "text/plain")}
    data = {"format": fmt, "duration_s": "2", "width": "640", "height": "360",
            "fps": "10", "background": "#101418", "crf": "40"}
    data.update({k: str(v) for k, v in form.items()})
    r = client.post("/render", files=files, data=data)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        st = client.get(f"/jobs/{job_id}").json()
        if st["state"] in {"done", "failed", "canceled"}:
            return st
        time.sleep(0.5)
    raise AssertionError("Job wurde nicht fertig")


def probe(path: Path, entries: str) -> str:
    # ffprobe braucht die Sektion: "codec_name" allein liefert NICHTS (der
    # Test schlug damit scheinbar wegen fehlender Untertitel fehl).
    if "=" not in entries:
        entries = f"stream={entries}"
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout
    return out.strip()


def frame_rgba(path: Path, at_s: float = 1.0, w: int = 640, h: int = 360):
    # Für WebM den libvpx-Dekoder erzwingen: der native vp9-Dekoder liefert in
    # dieser ffmpeg-Version das Bild ohne Alphakanal (gemessen), der
    # libvpx-Dekoder wendet den Alpha-Nebenstrom an.
    dec = []
    if path.suffix == ".webm":
        dec = ["-c:v", "libvpx-vp9"]
    out = subprocess.run(
        # Das KONFIGURIERTE ffmpeg benutzen: das System-ffmpeg (7.1) kann
        # HEVC-Alpha nicht dekodieren und liefert dann alles deckend.
        [render_app.FFMPEG, "-hide_banner", "-loglevel", "error", *dec, "-ss", str(at_s),
         "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True,
    )
    buf = out.stdout
    assert len(buf) == w * h * 4, f"unerwartete Bildgröße: {len(buf)}"
    return np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)


# --------------------------------------------------------------------------
# Aufbau / Formate
# --------------------------------------------------------------------------
def test_health_meldet_verfuegbare_formate(client):
    h = client.get("/health").json()
    assert h["libass"] is True, "libass fehlt — das Image wäre unbrauchbar"
    ids = [f["id"] for f in h["formats"]]
    for fmt in ("burn_mp4", "screen_mp4", "chroma_mp4", "alpha_webm", "alpha_mov"):
        assert fmt in ids
    # alpha_png nur, wenn der PNG-Encoder im Build steckt. Fehlt er, wird das
    # Format gar nicht angeboten — statt beim Rendern zu scheitern (das ist die
    # Absicherung, nicht ein Fehler). Der Image-Bau prueft den Encoder mit.
    if "png" in render_app.ENCODERS:
        assert "alpha_png" in ids
    # Alpha tragen nur die Alpha-Formate. hevc_alpha kommt nur dazu, wenn der
    # Dienst das kann — sonst wird es gar nicht angeboten.
    erwartet = {"alpha_webm", "alpha_mov", "alpha_png"}
    if render_app.x265_alpha_supported():
        erwartet.add("hevc_alpha")
    assert {f["id"] for f in h["formats"] if f["alpha"]} == erwartet
    for f in h["formats"]:
        assert f["ext"] and f["mime"] and f["label"]
        # Jedes Format muss sagen, wofuer es ist — die GUI zeigt diesen Text.
        assert f["note"], f"{f['id']} ohne Beschreibung"


def _args(fmt: str, ext: str):
    job = render_app.Job(id="x", format=fmt, filename=f"a.{ext}", dir=Path("/tmp"))
    return " ".join(render_app.build_ffmpeg_args(job, Path("/tmp/s.ass"), None,
                                                 1920, 1080, 25, 10.0, "#000000", 28))


def test_ffmpeg_argumente_je_format():
    joined = _args("alpha_webm", "webm")
    assert "libvpx-vp9" in joined and "yuva420p" in joined
    assert "-auto-alt-ref 0" in joined, "VP9-Alpha braucht -auto-alt-ref 0"
    assert "alpha_mode=1" in joined, "ohne alpha_mode zeigt der Player kein Alpha"
    assert joined.rstrip().endswith("a.webm")
    assert "color=c=black@0.0" in joined, "Alpha-Formate brauchen einen transparenten Untergrund"

    joined = _args("alpha_mov", "mov")
    assert "prores_ks" in joined and "yuva444p10le" in joined and "4444" in joined

    joined = _args("burn_mp4", "mp4")
    assert "libx264" in joined and "yuv420p" in joined
    assert "yuva" not in joined, "gebranntes MP4 darf keinen Alpha-Kanal erwarten"

    # Alpha-Formate muessen den Alphakanal des ass-Filters aktivieren.
    assert ":alpha=1" in _args("alpha_webm", "webm")
    assert ":alpha=1" in _args("alpha_mov", "mov")
    assert ":alpha=1" not in _args("burn_mp4", "mp4")
    # Kein Shell-String: Argumente gehen als Liste raus.
    job = render_app.Job(id="x", format="burn_mp4", filename="a.mp4", dir=Path("/tmp"))
    assert all(isinstance(a, str) for a in render_app.build_ffmpeg_args(
        job, Path("/tmp/s.ass"), None, 1920, 1080, 25, 10.0, "#000000", 28))


# --------------------------------------------------------------------------
# Der eigentliche Nachweis
# --------------------------------------------------------------------------
def test_alpha_webm_ist_wirklich_transparent(client, tmp_path):
    st = run_job(client, "alpha_webm")
    assert st["state"] == "done", st["error"]
    assert st["progress"] == 1.0
    r = client.get(f"/jobs/{st['id']}/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video/webm")
    f = tmp_path / "out.webm"
    f.write_bytes(r.content)

    # VP9 speichert Alpha als Nebentrom: ffprobe meldet die Farbebene als
    # yuv420p, das Alpha kennzeichnet ALPHA_MODE=1.
    tags = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream_tags=alpha_mode,stream=pix_fmt", "-of", "default=nw=1", str(f)],
        capture_output=True, text=True).stdout
    assert "alpha_mode=1" in tags.lower(), f"kein Alpha-Nebenstrom: {tags}"

    # Frame dekodieren und Alpha auswerten: transparent neben dem Text,
    # deckend auf dem Text.
    px = frame_rgba(f)
    alpha = px[:, :, 3]
    transparent = float((alpha == 0).mean())
    opaque = float((alpha > 200).mean())
    assert transparent > 0.5, f"zu wenig Transparenz: {transparent:.2%}"
    assert opaque > 0.0005, f"kein sichtbarer Text: {opaque:.4%}"
    # Und auf dem Text stehen wirklich helle Pixel (weiße Schrift), nicht nur
    # die schwarze Kontur: Maximum statt Mittelwert, sonst misst man die Kontur.
    ys, xs = np.where(alpha > 200)
    rgb = px[ys, xs, :3]
    assert int(rgb.max()) > 200, f"keine helle Schrift gefunden: max={int(rgb.max())}"


def test_alpha_mov_hat_alpha_und_prores4444(client, tmp_path):
    st = run_job(client, "alpha_mov")
    assert st["state"] == "done", st["error"]
    f = tmp_path / "out.mov"
    f.write_bytes(client.get(f"/jobs/{st['id']}/file").content)
    pix = probe(f, "pix_fmt")
    assert pix.startswith("yuva"), f"kein Alpha: {pix}"
    assert probe(f, "codec_name") == "prores"
    px = frame_rgba(f)
    assert float((px[:, :, 3] == 0).mean()) > 0.5, "Hintergrund ist nicht transparent"


def test_burn_mp4_brennt_die_untertitel_ein(client, tmp_path):
    st = run_job(client, "burn_mp4")
    assert st["state"] == "done", st["error"]
    f = tmp_path / "out.mp4"
    f.write_bytes(client.get(f"/jobs/{st['id']}/file").content)
    assert probe(f, "codec_name") == "h264"
    assert "yuva" not in probe(f, "pix_fmt")
    px = frame_rgba(f)
    gray = px[:, :, :3].mean(axis=2)
    # Text ist deutlich heller als der dunkle Hintergrund.
    assert float((gray > 200).mean()) > 0.0005, "keine eingebrannten Untertitel sichtbar"


# --------------------------------------------------------------------------
# Fehlerwege
# --------------------------------------------------------------------------
def test_unbekanntes_format_wird_abgelehnt(client):
    r = client.post("/render", files={"ass": ("u.ass", ASS.encode(), "text/plain")},
                    data={"format": "gibt_es_nicht", "duration_s": "1"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unsupported_format"


def test_keine_ass_datei_wird_abgelehnt(client):
    r = client.post("/render", files={"ass": ("u.txt", b"kein ass", "text/plain")},
                    data={"format": "alpha_webm", "duration_s": "1"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_ass"


def test_datei_vor_fertigstellung_ist_409(client):
    r = client.post("/render", files={"ass": ("u.ass", ASS.encode(), "text/plain")},
                    data={"format": "alpha_webm", "duration_s": "2"})
    job_id = r.json()["id"]
    fr = client.get(f"/jobs/{job_id}/file")
    if fr.status_code != 200:          # kann bei sehr kurzen Jobs schon fertig sein
        assert fr.status_code in (409, 200)


def test_unbekannter_job_ist_404(client):
    assert client.get("/jobs/gibtsnicht").status_code == 404
    assert client.get("/jobs/gibtsnicht/file").status_code == 404


def test_dateiname_wird_nicht_doppelt_gehaengt(client):
    """Live gefunden: "folge.webm" als ASS-Name ergab "folge.webm.webm"."""
    r = client.post("/render", files={"ass": ("folge.webm.ass", ASS.encode(), "text/plain")},
                    data={"format": "alpha_webm", "duration_s": "1"})
    assert r.status_code == 202, r.text
    assert r.json()["filename"] == "folge.webm"

    r = client.post("/render", files={"ass": ("treffen.ass", ASS.encode(), "text/plain")},
                    data={"format": "alpha_mov", "duration_s": "1"})
    assert r.json()["filename"] == "treffen.mov"


# ---------------------------------------------------------------------------
# Neustart-Festigkeit (live gefunden am 18.09.: Download brach ab)
# ---------------------------------------------------------------------------
def test_auftrag_ueberlebt_einen_neustart(client):
    """Nach einem Neustart war eine fertige Datei unauffindbar (unknown_job)."""
    st = run_job(client, "alpha_webm")
    assert st["state"] == "done"
    assert (render_app.DATA_DIR / st["id"] / "job.json").exists(), "Zustand nicht gesichert"

    # Neustart nachstellen: Gedaechtnis leeren, Wiederherstellung laufen lassen.
    with render_app.JOBS_LOCK:
        render_app.JOBS.clear()
    assert render_app._recover_jobs() >= 1

    st2 = client.get(f"/jobs/{st['id']}").json()
    assert st2["state"] == "done", st2
    assert st2["filename"] == st["filename"]
    r = client.get(f"/jobs/{st['id']}/file")
    assert r.status_code == 200
    assert len(r.content) == st2["size_bytes"] > 0


def _schreibe_altes_verzeichnis(jid: str, *, dauer_datei: float, dauer_erwartet: float) -> None:
    """Verzeichnis wie ein Lauf VOR dieser Aenderung (nur meta.json)."""
    d = render_app.DATA_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "format": "alpha_webm", "duration_s": dauer_erwartet, "width": 640,
        "height": 360, "fps": 10, "media": "", "background": "#101418", "crf": 40,
    }), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=black@0.0:s=640x360:r=10:d={dauer_datei},format=yuva420p",
         "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
         "-b:v", "0", "-crf", "40", "-t", str(dauer_datei), str(d / "untertitel.webm")],
        check=True)


def test_unvollstaendige_datei_wird_nie_ausgeliefert(client):
    """Der gemeldete Abbrich: 3 s gerechnet, 30 s erwartet -> nicht ausliefern."""
    _schreibe_altes_verzeichnis("abgeschnitten1234", dauer_datei=3.0, dauer_erwartet=30.0)
    with render_app.JOBS_LOCK:
        render_app.JOBS.clear()
    render_app._recover_jobs()

    st = client.get("/jobs/abgeschnitten1234").json()
    assert st["state"] == "failed", st
    assert "unvollstaendig" in st["error"] or "unterbrochen" in st["error"]
    assert client.get("/jobs/abgeschnitten1234/file").status_code == 409


def test_vollstaendige_alte_datei_wird_wieder_ausgeliefert(client):
    """Was vollstaendig auf der Platte liegt, bleibt nutzbar."""
    _schreibe_altes_verzeichnis("vollstaendig5678", dauer_datei=5.0, dauer_erwartet=5.0)
    with render_app.JOBS_LOCK:
        render_app.JOBS.clear()
    render_app._recover_jobs()

    st = client.get("/jobs/vollstaendig5678").json()
    assert st["state"] == "done", st
    r = client.get("/jobs/vollstaendig5678/file")
    assert r.status_code == 200 and len(r.content) == st["size_bytes"] > 0


def _tonquelle(tmp_path):
    """Kleine MP3 wie eine Polyschnack-Aufnahme: nur Ton, kein Bild."""
    f = tmp_path / "aufnahme.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=2", "-c:a", "libmp3lame",
                    "-b:a", "64k", str(f)], check=True)
    return ("aufnahme.mp3", f.read_bytes(), "audio/mpeg")


def _ton_spur(path: Path) -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout
    return out.strip()


def test_burn_mp4_mit_tonaufnahme_hat_wirklich_bild(client, tmp_path):
    """Gemeldeter Fehler (18.09.): Aufnahme ist nur Ton -> MP4 OHNE Videospur.

    Vorher lief der Videofilter ins Leere, weil als einzige Eingabe die Tondatei
    uebergeben wurde. Das Ergebnis war eine reine Audiodatei im MP4-Gewand — in
    KineMaster und jedem Schnittprogramm unbrauchbar.
    """
    files = {"ass": ("untertitel.ass", ASS.encode("utf-8"), "text/plain"),
             "media": _tonquelle(tmp_path)}
    r = client.post("/render", files=files, data={
        "format": "burn_mp4", "duration_s": "2", "width": "640", "height": "360",
        "fps": "10", "background": "#101418", "crf": "40"})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    for _ in range(120):
        st = client.get(f"/jobs/{job_id}").json()
        if st["state"] in {"done", "failed", "canceled"}:
            break
        time.sleep(0.5)
    assert st["state"] == "done", st["error"]

    f = tmp_path / "out.mp4"
    f.write_bytes(client.get(f"/jobs/{job_id}/file").content)
    assert probe(f, "codec_name") == "h264", "keine Videospur — genau der gemeldete Fehler"
    assert probe(f, "pix_fmt") == "yuv420p"
    assert _ton_spur(f) == "aac", "der Ton der Aufnahme fehlt"
    gray = frame_rgba(f)[:, :, :3].mean(axis=2)
    assert float((gray > 200).mean()) > 0.0005, "keine Untertitel im Bild"


def test_chroma_mp4_hat_gruenen_grund_und_text(client, tmp_path):
    """KineMaster-Weg: gruener Hintergrund zum Freistellen per Chroma Key."""
    st = run_job(client, "chroma_mp4", chroma_color="#00B140")
    assert st["state"] == "done", st["error"]
    f = tmp_path / "chroma.mp4"
    f.write_bytes(client.get(f"/jobs/{st['id']}/file").content)

    assert probe(f, "codec_name") == "h264"
    assert probe(f, "pix_fmt") == "yuv420p"
    px = frame_rgba(f)
    r_, g_, b_ = (int(v) for v in px[5, 5, :3])
    assert g_ > 60 and g_ > r_ + 30 and g_ > b_ + 30, f"Hintergrund nicht grün: {r_},{g_},{b_}"
    gray = px[:, :, :3].mean(axis=2)
    assert float((gray > 200).mean()) > 0.0005, "keine Untertitel sichtbar"


def test_screen_mp4_schwarzer_grund_fuer_mischmodus(client, tmp_path):
    """Handy-Weg ohne Chroma Key: schwarzer Grund, den »Screen« verschwinden laesst."""
    st = run_job(client, "screen_mp4", background="#FFFFFF")   # Hintergrund wird erzwungen
    assert st["state"] == "done", st["error"]
    f = tmp_path / "screen.mp4"
    f.write_bytes(client.get(f"/jobs/{st['id']}/file").content)
    assert probe(f, "codec_name") == "h264"
    px = frame_rgba(f)
    ecke = px[5, 5, :3].mean()
    assert ecke < 30, f"Hintergrund ist nicht schwarz: {ecke}"
    gray = px[:, :, :3].mean(axis=2)
    assert float((gray > 200).mean()) > 0.0005, "keine Untertitel sichtbar"


# ---------------------------------------------------------------------------
# HEVC mit Alpha (das Format, das KineMaster importiert)
# ---------------------------------------------------------------------------
def test_hevc_alpha_wird_ohne_faehigkeit_nicht_angeboten(client, monkeypatch):
    """Ein Format, das nicht geht, darf gar nicht erst erscheinen."""
    monkeypatch.setattr(render_app, "_X265_ALPHA_CACHE", None)
    monkeypatch.setattr(render_app, "x265_alpha_supported", lambda: False)
    monkeypatch.setitem(render_app._CAPABILITIES, "x265_alpha", lambda: False)
    ids = [f["id"] for f in client.get("/health").json()["formats"]]
    assert "hevc_alpha" not in ids
    assert "alpha_webm" in ids, "andere Alpha-Formate muessen bleiben"


def test_hevc_alpha_argumente_und_angebot(client, monkeypatch):
    """Mit Faehigkeit erscheint es und erzeugt HEVC mit yuva420p."""
    monkeypatch.setitem(render_app._CAPABILITIES, "x265_alpha", lambda: True)
    ids = [f["id"] for f in client.get("/health").json()["formats"]]
    assert "hevc_alpha" in ids

    job = render_app.Job(id="x", format="hevc_alpha", filename="a.mp4", dir=Path("/tmp"))
    args = " ".join(render_app.build_ffmpeg_args(job, Path("/tmp/s.ass"), None,
                                                 1920, 1080, 25, 10.0, "#000000", 28))
    assert "libx265" in args
    assert "-pix_fmt yuva420p" in args, "ohne yuva420p gibt es kein Alpha"
    assert "-tag:v hvc1" in args, "KineMaster erwartet den Apple-Tag"


def test_hevc_alpha_erzeugt_echte_transparenz(client):
    """Voller Weg — laeuft nur mit Alpha-faehigem ffmpeg (im Image, nicht lokal).

    Der Image-Bau prueft dieselbe Kette (ffalpha-build/Dockerfile): ohne
    nachgewiesene Transparenz scheitert dort schon der Build.
    """
    if not render_app.x265_alpha_supported():
        pytest.skip("ffmpeg ohne HEVC-Alpha — wird im ffalpha-Image geprueft")
    st = run_job(client, "hevc_alpha")
    assert st["state"] == "done", st["error"]
    datei = Path(render_app.DATA_DIR) / st["id"] / st["filename"]
    assert datei.exists()
    px = frame_rgba(datei)
    assert (px[:, :, 3] < 10).mean() > 0.5, "Hintergrund ist nicht transparent"
    assert (px[:, :, 3] > 200).mean() > 0.0001, "kein deckender Text gefunden"
