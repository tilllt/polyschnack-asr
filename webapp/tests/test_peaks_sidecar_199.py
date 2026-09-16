"""Change 199: Sidecar-Envelopes für die Detailwellenform im Wort-Timing.

Zwei binäre uint8-Envelopes neben dem Audio, geschrieben aus dem einen
Peaks-Dekodierlauf:
  *_peaks_hi.bin   1000 Bins/s (ein Bin pro Millisekunde) — Wort-Zoom
  *_peaks_res.bin  residentes Level unter RESIDENT_BIN_BUDGET — ganz laden

Die Kernfunktionen sind pur (kein ffmpeg); nur das Schreiben der Sidecars
braucht eine echte Datei.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from app.peaks import (
    HI_BPS,
    PEAK_COUNT,
    RESIDENT_BIN_BUDGET,
    bins_per_second_resident,
    envelope_from_s16le,
    envelope_to_floats,
    hi_bin_count,
    peaks_from_s16le,
    peaks_sidecar_paths,
    pool_envelope,
    read_envelope,
    resident_bin_count,
    write_peaks_sidecars,
)

_2_25 = 33_554_428  # gemessene Browser-Breitengrenze (2^25 px)


def _s16le(samples) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _chunks(raw: bytes, size: int = 1 << 16):
    for i in range(0, len(raw), size):
        yield raw[i:i + size]


def _wav(path, seconds: float, sr: int = 16000, amp: float = 0.5) -> None:
    """Echte 16-kHz-mono-WAV-Datei mit einem Sinus schreiben."""
    n = int(sr * seconds)
    t = np.arange(n)
    sig = (np.sin(2 * np.pi * 440 * t / sr) * amp * 32767).astype("<i2")
    data = sig.tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(data))
    path.write_bytes(hdr + data)


# ── Envelope-Grundlagen ───────────────────────────────────────────────────


def test_envelope_liefert_uint8_mit_der_angefragten_laenge():
    total = 20000
    raw = _s16le([32767] * total)
    env = envelope_from_s16le(_chunks(raw), total, 2000)
    assert env.dtype == np.uint8
    assert env.size == 2000
    assert env.max() == 255


def test_envelope_entspricht_den_float_peaks_bis_auf_quantisierung():
    """Die uint8-Quantisierung VOR dem Maximum muss verlustfrei sein.

    floor ist monoton, also gilt max(floor(x)) == floor(max(x)) — die
    Abweichung darf höchstens eine Stufe (1/255) betragen.
    """
    total = PEAK_COUNT * 8
    rng = np.random.default_rng(11)
    samples = rng.integers(-32768, 32767, total, dtype=np.int16)
    raw = samples.astype("<i2").tobytes()
    env = envelope_from_s16le(_chunks(raw), total, PEAK_COUNT)
    floats = np.array(peaks_from_s16le(_chunks(raw), total, PEAK_COUNT),
                      dtype=np.float32)
    diff = np.abs(env.astype(np.float32) / 255.0 - floats).max()
    assert diff <= 1 / 255 + 1e-6, diff


def test_envelope_chunked_gleich_einmal():
    total = PEAK_COUNT * 8
    rng = np.random.default_rng(5)
    raw = rng.integers(-32768, 32767, total, dtype=np.int16).astype("<i2").tobytes()
    one = envelope_from_s16le([raw], total, PEAK_COUNT)
    many = envelope_from_s16le(_chunks(raw, 5000), total, PEAK_COUNT)
    assert np.array_equal(one, many)


def test_envelope_kappt_den_sonderwert_statt_umzulaufen():
    """abs(-32768) = 32768 → >>7 = 256 würde auf 0 umlaufen (stille Spitze)."""
    env = envelope_from_s16le([_s16le([-32768])], 1, 1)
    assert int(env[0]) == 255


def test_envelope_leere_und_kurze_eingaben():
    env = envelope_from_s16le([b"", _s16le([100, 200])], 2, 10)
    assert env.size == 10
    assert env.max() == int(200 >> 7)


# ── Pooling ───────────────────────────────────────────────────────────────


def test_pool_envelope_ist_maximum_je_gruppe():
    env = np.zeros(1000, dtype=np.uint8)
    env[333] = 200   # fällt in die zweite der drei Gruppen
    out = pool_envelope(env, 3)
    assert out.tolist() == [0, 200, 0]


def test_pool_envelope_nach_oben_bleibt_unveraendert():
    env = np.arange(100, dtype=np.uint8)
    assert pool_envelope(env, 1000) is env


def test_pool_envelope_erhaelt_die_spitze():
    env = np.zeros(5000, dtype=np.uint8)
    env[4999] = 255
    out = pool_envelope(env, 2000)
    assert out.size == 2000
    assert int(out[-1]) == 255


# ── Budget-Formel ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("duration_s", [60.0, 600.0, 3600.0, 15718.0, 36000.0])
def test_residentes_budget_ist_von_der_dauer_unabhaengig(duration_s):
    """Die Nutzlast ist die Invariante, nicht die Auflösung.

    Bei langen Dateien liefert das Budget immer dieselbe Bin-Zahl (und damit
    dieselbe Balkenzahl im Maximalzoom), weil sich die Dauer herauskürzt.
    """
    bins = resident_bin_count(duration_s)
    assert bins <= RESIDENT_BIN_BUDGET
    if bins_per_second_resident(duration_s) < HI_BPS:
        assert bins == RESIDENT_BIN_BUDGET
    # Balken im Maximalzoom bei 1000 px — unabhängig von der Dauer
    bars = bins * 1000 / _2_25
    if bins_per_second_resident(duration_s) < HI_BPS:
        assert abs(bars - RESIDENT_BIN_BUDGET * 1000 / _2_25) < 1e-6


def test_residentes_budget_deckelt_kurze_dateien_auf_die_detailaufloesung():
    """Unter ~35 min greift das Budget nicht — dann gilt die Detailauflösung."""
    assert bins_per_second_resident(600.0) == float(HI_BPS)
    assert resident_bin_count(600.0) == hi_bin_count(600.0)


def test_hi_bins_sind_ein_bin_pro_millisekunde():
    assert hi_bin_count(15718.0) == 15_718_000
    assert hi_bin_count(0.5) == 500


def test_residentes_level_sinkt_mit_der_laenge():
    assert bins_per_second_resident(15718.0) < bins_per_second_resident(3600.0) < HI_BPS


def test_json_ableitung_repraesentiert_die_peaks():
    """Der 2000er-Vektor kommt aus dem residenten Sidecar, nicht aus einem
    zweiten Dekodierlauf — er muss die Form trotzdem treffen."""
    total = 16000 * 30
    rng = np.random.default_rng(7)
    raw = rng.integers(-32768, 32767, total, dtype=np.int16).astype("<i2").tobytes()
    env = envelope_from_s16le(_chunks(raw), total, hi_bin_count(30.0))
    aus_sidecar = np.array(envelope_to_floats(env, PEAK_COUNT), dtype=np.float32)
    direkt = np.array(peaks_from_s16le(_chunks(raw), total, PEAK_COUNT),
                      dtype=np.float32)
    assert aus_sidecar.size == PEAK_COUNT
    # Die Gruppengrenzen verschieben sich um höchstens einen Detail-Bin (1 ms),
    # das Maximum darf dadurch nur nach oben abweichen — nie nach unten.
    assert (aus_sidecar >= direkt - 1 / 255).all()
    assert np.abs(aus_sidecar - direkt).mean() < 0.02


# ── Sidecars schreiben ────────────────────────────────────────────────────


def test_write_peaks_sidecars_schreibt_beide_ebenen(tmp_path):
    src = tmp_path / "aufnahme.wav"
    _wav(src, seconds=12.0)
    info = write_peaks_sidecars(src)
    assert info is not None
    hi, res = peaks_sidecar_paths(src)
    assert info["hi_path"] == str(hi)
    assert hi.exists() and hi.stat().st_size == info["hi_bins"]
    assert info["hi_bins"] == hi_bin_count(12.0) == 12000
    # 12 s < Budget-Grenze → residente Auflösung = Detailauflösung,
    # dann zeigen beide Ebenen auf dieselbe Datei (kein doppelter Speicher).
    assert info["res_path"] == str(hi)
    assert not res.exists()
    assert not info["cached"]


def test_write_peaks_sidecars_ist_idempotent(tmp_path):
    src = tmp_path / "aufnahme.wav"
    _wav(src, seconds=8.0)
    first = write_peaks_sidecars(src)
    assert first and not first["cached"]
    hi, _ = peaks_sidecar_paths(src)
    stamp = hi.stat().st_mtime_ns
    second = write_peaks_sidecars(src)
    assert second is not None and second["cached"] is True
    assert hi.stat().st_mtime_ns == stamp, "Sidecar wurde ohne Grund neu geschrieben"


def test_write_peaks_sidecars_ersetzt_abgeschnittene_datei(tmp_path):
    """Eine halbe Datei (abgebrochener Lauf) darf nicht als gültig gelten."""
    src = tmp_path / "aufnahme.wav"
    _wav(src, seconds=6.0)
    hi, _ = peaks_sidecar_paths(src)
    hi.write_bytes(b"\x00" * 100)  # falsche Länge
    info = write_peaks_sidecars(src)
    assert info is not None and info["cached"] is False
    assert hi.stat().st_size == info["hi_bins"]


def test_write_peaks_sidecars_ohne_dekodierbare_datei(tmp_path):
    src = tmp_path / "kaputt.wav"
    src.write_bytes(b"kein audio")
    assert write_peaks_sidecars(src) is None


def test_read_envelope_liest_das_sidecar(tmp_path):
    p = tmp_path / "x_peaks_hi.bin"
    p.write_bytes(bytes([0, 128, 255]))
    env = read_envelope(p)
    assert env is not None and env.tolist() == [0, 128, 255]
    assert read_envelope(tmp_path / "fehlt.bin") is None
    (tmp_path / "leer.bin").write_bytes(b"")
    assert read_envelope(tmp_path / "leer.bin") is None


# ── Endpunkt ──────────────────────────────────────────────────────────────


class _Rec:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _call_endpoint(tmp_path, monkeypatch, level, rec):
    import app.routers.recordings as R

    monkeypatch.setattr(R, "get_recording_by_uid", lambda s, r: rec)
    monkeypatch.setattr(R, "_current_user", lambda req, s: 1)
    # _key_cap wird beim Aufruf von ensure_access ausgewertet (Argument),
    # greift also VOR dem Patch von ensure_access — deshalb separat ersetzen.
    monkeypatch.setattr(R, "_key_cap", lambda req, s: None)
    monkeypatch.setattr(R, "ensure_access", lambda *a, **k: None)
    return R.get_peaks_binary("uid", request=None, level=level, session=None)


def test_endpunkt_level_hi_liefert_das_detail_sidecar(tmp_path, monkeypatch):
    from fastapi.responses import FileResponse

    src = tmp_path / "a.wav"
    _wav(src, seconds=5.0)
    info = write_peaks_sidecars(src)
    rec = _Rec(peaks_hi_path=info["hi_path"], peaks_res_path=info["res_path"])
    resp = _call_endpoint(tmp_path, monkeypatch, "hi", rec)
    assert isinstance(resp, FileResponse)
    assert resp.path == info["hi_path"]
    assert resp.media_type == "application/octet-stream"
    assert resp.headers["x-peaks-level"] == "hi"


def test_endpunkt_level_res_ist_die_vorgabe(tmp_path, monkeypatch):
    src = tmp_path / "a.wav"
    _wav(src, seconds=5.0)
    info = write_peaks_sidecars(src)
    rec = _Rec(peaks_hi_path=info["hi_path"], peaks_res_path=info["res_path"])
    resp = _call_endpoint(tmp_path, monkeypatch, "res", rec)
    assert resp.path == info["res_path"]


def test_endpunkt_ohne_sidecar_gibt_404(tmp_path, monkeypatch):
    from fastapi import HTTPException

    rec = _Rec(peaks_hi_path=None, peaks_res_path=None)
    with pytest.raises(HTTPException) as e:
        _call_endpoint(tmp_path, monkeypatch, "res", rec)
    assert e.value.status_code == 404


def test_endpunkt_meldet_fehlende_datei_als_404(tmp_path, monkeypatch):
    from fastapi import HTTPException

    rec = _Rec(peaks_hi_path=str(tmp_path / "weg.bin"),
               peaks_res_path=str(tmp_path / "weg.bin"))
    with pytest.raises(HTTPException) as e:
        _call_endpoint(tmp_path, monkeypatch, "hi", rec)
    assert e.value.status_code == 404


def test_endpunkt_antwort_ist_range_faehig(tmp_path):
    """Ein Detailfenster wird per Range angeschnitten — 206 + content-range."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient

    src = tmp_path / "a.wav"
    _wav(src, seconds=3.0)
    info = write_peaks_sidecars(src)
    p = info["hi_path"]

    app = FastAPI()

    @app.get("/bin")
    def _bin():
        return FileResponse(p, media_type="application/octet-stream")

    with TestClient(app) as c:
        full = c.get("/bin")
        assert full.status_code == 200
        assert len(full.content) == info["hi_bins"]
        part = c.get("/bin", headers={"Range": "bytes=1000-1999"})
        assert part.status_code == 206
        assert part.headers["content-range"] == f"bytes 1000-1999/{info['hi_bins']}"
        assert len(part.content) == 1000
        # 1 s Detailfenster bei 1000 Bins/s ist genau 1000 Byte — nicht 6 MB.
        ueberhang = c.get("/bin", headers={"Range": f"bytes=0-{info['hi_bins'] + 500}"})
        assert ueberhang.status_code == 206
        assert len(ueberhang.content) == info["hi_bins"]
