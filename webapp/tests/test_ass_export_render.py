"""Change 193 — ASS-Export: Beweis am echten Renderer (libass via ffmpeg).

Ein grüner Struktur-Test beweist nur, dass eine Datei nach ASS *aussieht*.
Diese Tests rendern die erzeugten Dateien mit libass über einen schwarzen
Clip und messen die Bildpunkte:

* presets ohne libass-Fehler ladbar,
* Captions werden tatsächlich gezeichnet (und nur während der Events),
* Karaoke füllt sich wirklich progressiv (Farbverlauf statt Sprung),
* Hervorhebung wandert wirklich zum nächsten Wort (Schwerpunkt wandert rechts),
* Aufpoppen startet wirklich gross und schrumpft,
* Social Media blendet Wörter wirklich nacheinander ein.

Damit sind die Werbeaussagen der Presets („füllt sich", „poppt", „erscheint
Wort für Wort") gemessen statt behauptet. Läuft ohne ffmpeg/numpy übersprungen.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

np = pytest.importorskip("numpy")

from app.ass_export import generate_ass  # noqa: E402
from tests.test_ass_export import ALL_PRESETS, recording, seg  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg (mit libass) fehlt")

WIDTH, HEIGHT, FPS = 640, 360, 20
LIBASS_ERRORS = ("Could not find style", "Parse error", "ASS_Style",
                 "ass_read_file failed", "Invalid", "invalid")


def sample_recording():
    """Drei Wörter mit klar getrennten Zeiten (0.0-0.3-0.6-1.2 s)."""
    return recording([seg(0.0, 1.2, [("Ein", 0.0, 0.3),
                                     ("zwei", 0.3, 0.6),
                                     ("drei", 0.6, 1.1)])], name="render.mp3")


def render(ass_text: str, tmp_path: Path, duration: float,
           fps: int = FPS) -> "np.ndarray":
    """ASS über schwarzen Clip rendern → ``(frames, h, w, 3)`` uint8."""
    (tmp_path / "captions.ass").write_text(ass_text, encoding="utf-8")
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "warning",
         "-f", "lavfi", "-i", f"color=black:s={WIDTH}x{HEIGHT}:d={duration}:r={fps}",
         "-vf", "ass=captions.ass", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        cwd=tmp_path, capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"ffmpeg scheiterte: {proc.stderr.decode()[:400]}")
    frames = np.frombuffer(proc.stdout, dtype=np.uint8)
    frames = frames[: (len(frames) // (WIDTH * HEIGHT * 3)) * (WIDTH * HEIGHT * 3)]
    return frames.reshape(-1, HEIGHT, WIDTH, 3), proc.stderr.decode()


def lit_mask(frame) -> "np.ndarray":
    """Maske der gezeichneten (nicht-schwarzen) Bildpunkte eines Frames."""
    return frame.sum(axis=2) > 60


def lit_count(frame) -> int:
    return int(lit_mask(frame).sum())


def accent_mask(frame, rgb=(255, 212, 0)):
    """Bildpunkte nahe der Akzentfarbe (#FFD400)."""
    diff = np.abs(frame.astype(int) - np.array(rgb))
    return (diff.max(axis=2) < 60) & (frame.sum(axis=2) > 120)


# ---------------------------------------------------------------------------
# libass nimmt jede Preset-Datei an
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset", ALL_PRESETS)
def test_libass_accepts_every_preset(preset, tmp_path):
    ass = generate_ass(sample_recording(), preset).content
    frames, stderr = render(ass, tmp_path, duration=1.6)
    assert len(frames) > 0
    for needle in LIBASS_ERRORS:
        assert needle not in stderr, f"{preset}: libass meldet {stderr.strip()!r}"
    assert lit_count(frames[4]) > 0, f"{preset}: kein einziger Bildpunkt gezeichnet"


@pytest.mark.parametrize("preset", ALL_PRESETS)
def test_captions_only_visible_during_events(preset, tmp_path):
    """Nach dem letzten Event (und dessen Nachlauf) ist das Bild wieder schwarz."""
    ass = generate_ass(sample_recording(), preset, {"tail_ms": 0}).content
    frames, _ = render(ass, tmp_path, duration=2.0)
    assert lit_count(frames[10]) > 0        # mitten im Event (0.5 s)
    assert lit_count(frames[-2]) == 0       # 1.9 s: alles vorbei


def test_documented_brace_handling_shows_up_on_screen(tmp_path):
    """Beweis für den Klammer-Ersatz: das Wort hinter {…} kommt im Bild an.

    libass rendert ``A{B}C`` wie ``AC`` (verschluckt den Block). PolySchnack
    ersetzt die Klammern — hier wird geprüft, dass der Text dadurch sichtbar
    breiter wird als mit dem verschluckten Block.
    """
    brace = recording([seg(0.0, 1.0, [("Wort", 0.0, 0.2), ("{klammer}", 0.3, 0.6)])])
    brace_ass = generate_ass(brace, "classic", {"tail_ms": 0, "fade_ms": 0}).content
    swallowed = brace_ass.replace("(klammer)", "{klammer}")
    frames_ok, _ = render(brace_ass, tmp_path, duration=0.5, fps=2)
    frames_bad, _ = render(swallowed, tmp_path, duration=0.5, fps=2)
    assert lit_count(frames_ok[0]) > lit_count(frames_bad[0]), (
        "Klammer-Ersatz wirkt nicht: Text wäre im Video kürzer/verschluckt"
    )


# ---------------------------------------------------------------------------
# Preset-Effekte messen
# ---------------------------------------------------------------------------


def test_karaoke_fill_is_progressive(tmp_path):
    """\\kf muss die Silbe füllen (Farbverlauf über die Zeit), nicht springen.

    Akzent rot, ungesungen weiss: die Menge roter Bildpunkte wächst über die
    Zeile, die weissen verschwinden. Gemessen (640x360, 20 fps): rot 160 → 654,
    weiss 381 → 10 — ein Sprung wäre kein Farbverlauf.
    """
    ass = generate_ass(sample_recording(), "karaoke", {
        "accent_color": "#FF0000", "dim_color": "#FFFFFF", "tail_ms": 0,
    }).content
    frames, _ = render(ass, tmp_path, duration=1.2)
    red, white = [], []
    for frame in frames[1:22]:  # Karaoke-Zeile 0.0-1.1 s
        pixels = frame[lit_mask(frame)]
        red.append(int((pixels[:, 1] < 100).sum()))
        white.append(int((pixels[:, 1] > 150).sum()))
    assert white[0] > 150 and red[0] < white[0], (
        f"Start nicht überwiegend ungesungen: rot={red[0]} weiss={white[0]}"
    )
    assert white[-1] < 40 and red[-1] > 400, (
        f"Ende nicht gefüllt: rot={red[-1]} weiss={white[-1]}"
    )
    # Fortschritt = Zwischenzustände (beide Farben sichtbar), kein Sprung.
    mixed = sum(1 for r, w in zip(red, white) if r > 100 and w > 100)
    assert mixed >= 5, f"kein Farbverlauf, sondern Sprung: {list(zip(red, white))}"
    # Grob monoton: Viertel-Marken müssen zunehmen.
    marks = [red[int(len(red) * f)] for f in (0.0, 0.25, 0.5, 0.75)]
    assert marks == sorted(marks), f"Füllung läuft nicht vorwärts: {marks}"


def test_highlight_moves_to_the_next_word(tmp_path):
    """Der Akzent muss innerhalb einer Zeile von Wort zu Wort wandern."""
    ass = generate_ass(sample_recording(), "highlight", {"tail_ms": 0}).content
    frames, _ = render(ass, tmp_path, duration=1.2)
    centroids = []
    for t in (0.15, 0.45, 0.75):  # Mitte jedes Wort-Schrittes
        frame = frames[int(t * FPS)]
        mask = accent_mask(frame)
        assert mask.sum() > 5, f"kein Akzent-Wort bei t={t}s"
        xs = np.where(mask)[1]
        centroids.append(float(xs.mean()))
    assert centroids[0] < centroids[1] < centroids[2], (
        f"Akzent wandert nicht nach rechts: {centroids}"
    )


def test_kinetic_active_word_starts_big_and_shrinks(tmp_path):
    """Aufpoppen: direkt nach Wortstart mehr Bildpunkte als nach pop_ms."""
    ass = generate_ass(sample_recording(), "kinetic", {
        "pop_scale": 160, "pop_ms": 200, "tail_ms": 0,
    }).content
    frames, _ = render(ass, tmp_path, duration=1.2)
    start = lit_count(frames[int(0.32 * FPS)])   # zweites Wort: Schritt-Start
    settled = lit_count(frames[int(0.52 * FPS)])  # 200 ms später
    assert start > settled, f"kein Aufpoppen: {start} → {settled} Bildpunkte"


def test_modern_reveals_words_one_after_another(tmp_path):
    """Social Media: sichtbare Bildpunkte wachsen innerhalb der Zeile."""
    ass = generate_ass(sample_recording(), "modern", {
        "words_per_line": 3, "sentence_breaks": False, "hide_upcoming": True,
        "tail_ms": 0,
    }).content
    frames, _ = render(ass, tmp_path, duration=1.2)
    counts = [lit_count(frames[int(t * FPS)]) for t in (0.15, 0.45, 0.75)]
    assert counts[0] < counts[1] < counts[2], (
        f"Wörter erscheinen nicht nacheinander: {counts}"
    )
