#!/usr/bin/env python3
"""PolySchnack Forced-Aligner-Service — schlanker HTTP-Wrapper um qwen3-asr-cli.

Nur Python-Stdlib (kein FastAPI/pip) — der Container bleibt klein.

Endpoints:
  GET  /health            -> {"status": "ok"}
  POST /v1/audio/align    -> Word-Level-Timestamps (JSON)
      multipart/form-data: file (Audio, beliebiges Format via ffmpeg),
                           text (Referenztext), lang (default "de")

Modell-Limit: max. 400 s Audio pro Request (qwen3-forced-aligner-Design:
5000 Zeitklassen x 80 ms Auflösung). Längere Audios schneidet der Aufrufer
in Chunks und sendet je Chunk den passenden Text (die Webapp nutzt ihre
120-s-ASR-Chunks -> passt 1:1).

Der Aligner ist ein einzelner, nicht-autoregressiver Forward-Pass — sehr
schnell (GPU RTF ~0.05-0.15). Nur ein Alignment gleichzeitig (Lock), da das
ggml-Modell resident geladen wird.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_AUDIO_S = 400.0
MAX_BODY_BYTES = 512 * 1024 * 1024  # 512 MB Upload-Limit
CLI_TIMEOUT_S = 900

#: Pfad der OpenAPI-Spec im Container (Dockerfile: COPY openapi.json /app/)
_OPENAPI_PATH = "/app/openapi.json"

#: Swagger-UI (CDN) — eingebettet, kein Node-Build nötig.
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="robots" content="noindex, nofollow" />
  <title>PolySchnack Forced-Aligner — API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>body { margin: 0; background: #0f172a; }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
    });
  </script>
</body>
</html>
"""

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Live-Job-Status (2026-08-15): ECHTE Lebenszeichen für die Webapp-UI.
# Der Aligner-CLI läuft blockierend; /status zeigt, dass der Prozess lebt
# (seit wann, letzte CLI-Zeile, ggml-Progress %). Kein Fake-Fortschritt:
# ohne CLI-Zeilen melden wir die vergangene Zeit — nie erfundene Prozente.
# ---------------------------------------------------------------------------
_JOB_STATUS: dict = {
    "active": False,
    "started_at": None,      # epoch-s (float) — für 'aktiv seit Xs'
    "last_beat_at": None,    # epoch-s — letzte CLI-Zeile (Herzschlag)
    "last_line": "",         # letzte ausgegebene CLI-Zeile (Live-Fenster)
    "progress_pct": None,    # nur wenn die CLI selbst % meldet
    "error": None,           # letzter Fehler (für Diagnose)
}
_JOB_LOCK = threading.Lock()


def _job_start() -> None:
    with _JOB_LOCK:
        _JOB_STATUS.update(
            active=True, started_at=time.time(), last_beat_at=time.time(),
            last_line="", progress_pct=None, error=None,
        )


def _job_beat(line: str) -> None:
    with _JOB_LOCK:
        _JOB_STATUS["last_beat_at"] = time.time()
        _JOB_STATUS["last_line"] = line[-160:]  # nur Tail, kein Speicherleck


def _job_progress(pct: int) -> None:
    with _JOB_LOCK:
        _JOB_STATUS["progress_pct"] = pct


def _job_finish(error: str | None = None) -> None:
    with _JOB_LOCK:
        _JOB_STATUS["active"] = False
        if error:
            _JOB_STATUS["error"] = error


def _job_snapshot() -> dict:
    """Kopierter Status für /status — nie die Live-Dict-Referenz rausgeben."""
    with _JOB_LOCK:
        snap = dict(_JOB_STATUS)
        snap["elapsed_s"] = (
            round(time.time() - snap["started_at"], 1)
            if snap["started_at"] and snap["active"] else 0
        )
        snap["last_beat_ago_s"] = (
            round(time.time() - snap["last_beat_at"], 1)
            if snap["last_beat_at"] and snap["active"] else None
        )
        return snap


def _probe_duration_s(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _to_wav16k(src: str, dst: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src,
         "-ar", "16000", "-ac", "1", "-f", "wav", dst],
        check=True, capture_output=True, timeout=300,
    )


def _parse_alignment(out_json: str, resolve: bool = True) -> list[dict]:
    """Tolerant parsen: JSON (words/segments/Liste) oder Zeilen 'start end word'.

    Reicht confidence durch (falls die CLI es liefert) und löst
    0-Dauer-Wörter auf (start==end → nächste Wortgrenze bzw. min. 80 ms).
    Mit resolve=False bleiben die ROH-Wörter erhalten (für die
    Energie-Korrektur, die VOR der Auflösung laufen muss).
    """
    words: list[dict] = []
    try:
        with open(out_json, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = data.get("words") or data.get("segments") or data.get("word_timestamps") or []
        if isinstance(data, list):
            for w in data:
                if not isinstance(w, dict):
                    continue
                item = {
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "word": w.get("word") or w.get("text") or "",
                }
                if w.get("confidence") is not None:
                    item["confidence"] = w.get("confidence")
                words.append(item)
        else:
            words = []
    except Exception:
        pass
    if not words:
        try:
            with open(out_json, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            words.append({
                                "start": float(parts[0]),
                                "end": float(parts[1]),
                                "word": " ".join(parts[2:]),
                            })
                        except ValueError:
                            continue
        except OSError:
            pass
    return _resolve_zero_duration(words) if resolve else words


def _resolve_zero_duration(words: list[dict]) -> list[dict]:
    """Text-Overflow-Artefakte auflösen: start==end (0-Dauer) bekommt die
    nächste Wortgrenze als end bzw. mindestens eine 80-ms-Zeitklasse
    (qwen3-forced-aligner-Auflösung: 5000 Klassen × 80 ms = 400 s).

    Ohne diesen Schritt wären Karaoke-Wort-Klicks auf solche Wörter
    wirkungslos (0-ms-Abspielbereich).
    """
    out: list[dict] = []
    for i, w in enumerate(words):
        item = dict(w)
        s, e = item.get("start"), item.get("end")
        if s is None:
            s = 0.0
        if e is None or e <= s:
            nxt = None
            if i + 1 < len(words):
                nxt = words[i + 1].get("start")
            e = nxt if (nxt is not None and nxt > s) else s + 0.08
        item["start"], item["end"] = s, e
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Energie-basierte Wortgrenzen-Korrektur (2026-08-17)
#
# Befund: qwen3-forced-aligner liefert für Wörter in künstlich langen Pausen
# (TTS-Ground-Truth mit 0.35 s Stille pro Wort) 0-Dauer-Intervalle
# (start == end). _resolve_zero_duration füllt dann end = nächster start —
# dadurch wird die KOMPLETTE Stille davor/danach dem Wort zugeschlagen und
# die Karaoke-Markierung bleibt viel zu lange aktiv ("Playback läuft den
# Markierungen hinterher").
#
# Lösung hier: Die CLI-Grenzen sind trotzdem meist akustisch plausibel
# (Starts ± 1-2 Bins korrekt, s. GT-Messung). Wir ziehen die Wortgrenzen an
# die echten Energie-Kanten der WAV: Jedes Wort [s, e] wird auf den
# nächstgelegenen akustisch belegten Bereich (RMS > Schwelle) begrenzt —
# die Stille gehört dann KEINEM Wort.
# ---------------------------------------------------------------------------
def _estimate_silence_rms(rms: list) -> float:
    """Change 078 (2026-08-21): Noisefloor-basierte Stille-Schwelle.

    Fester Wert (silence_rms=300) versagt bei historischen Aufnahmen mit
    starkem Grundrauschen: das Plattenrauschen liegt stellenweise ÜBER
    300 → der Speech-Detektor sieht fast alles als „Sprache" → keine
    Stille-Lücken → Wortgrenzen-Korrektur wirkungslos (gemessen an
    68026-moissi-hamlet.mp3: 1 Lücke statt 119 mit adaptiver Schwelle).

    Methode: Perzentil P15 der RMS-Frames (unterer Bereich = Grund-
    rauschen) × 1.8. P15 ist robust gegen einzelne laute Frames; der
    Faktor hebt die Schwelle deutlich über den Noisefloor, aber unter
    den Sprachpegel. Fallback 300, wenn die Analyse nichts hergibt.

    Kontrast-Schutz (Test-Fund 2026-08-21): Bei einem Signal OHNE
    Grundrauschen (z. B. synthetischer Sinus, P15 ≈ P85) läge P15×1.8
    ÜBER dem Signal → der Detektor sähe ALLES als Stille → leere
    Regionen → Wortenden kollabieren. Ist der Kontrast P85/P15 klein
    (< 2), gibt es keinen echten Noisefloor → Schwelle UNTER P15
    (×0.8), damit alles eine Region bleibt und die CLI-Wörter
    unverändert durchlaufen.
    """
    if not rms:
        return 300.0
    s = sorted(rms)
    n = len(s)
    p15 = s[min(n - 1, int(n * 0.15))]
    if p15 <= 0:
        return 300.0
    p85 = s[min(n - 1, int(n * 0.85))]
    if p85 / p15 >= 2.0:
        thresh = p15 * 1.8
    else:
        thresh = p15 * 0.8
    return max(30.0, min(thresh, 3000.0))


def _energy_refine(words: list[dict], wav_path: str,
                   frame_ms: float = 10.0, silence_rms: float | None = None,
                   min_gap_s: float = 0.25) -> list[dict]:
    """Zieht Wortgrenzen an echte Stille-Lücken (defensiv).

    Befund (2026-08-17, GT-Messung): qwen3-forced-aligner liefert für
    Wörter in künstlich langen Pausen 0-Dauer-Intervalle (start==end);
    _resolve_zero_duration füllt end = nächster start → die KOMPLETTE
    Stille davor/danach wird dem Wort zugeschlagen (Karaoke-Markierung
    bleibt viel zu lange aktiv).

    Lösung: Stille-Lücken > min_gap_s (deutlich größer als Konsonanten-
    Lücken ~20-40 ms) sind echte Wortgrenzen. Die Wörter werden den
    akustisch belegten REGIONEN zwischen den Lücken zugeordnet — die
    Stille gehört dann keinem Wort. Fehler beim WAV-Lesen → Wörter
    unverändert (nie ein Job-Fail, nie verschlechterte Zeiten).
    """
    if not wav_path or not os.path.exists(wav_path) or not words:
        return words
    try:
        import wave
        import struct

        with wave.open(wav_path, "rb") as wf:
            n_ch = wf.getnchannels()
            srate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if n_ch != 1 or srate <= 0:
            return words
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        frame_len = max(1, int(srate * frame_ms / 1000.0))
        rms: list[float] = []
        for i in range(0, len(samples), frame_len):
            chunk = samples[i:i + frame_len]
            if not chunk:
                break
            sq = sum(s * s for s in chunk) / len(chunk)
            rms.append((sq ** 0.5) or 0.0)
        # Change 078: adaptive Schwelle aus dem Noisefloor (P15×1.8),
        # falls kein expliziter Wert übergeben wurde.
        if silence_rms is None:
            silence_rms = _estimate_silence_rms(rms)
        speech = [r > silence_rms for r in rms]
        dt = frame_len / srate

        # Stille-Lücken > min_gap_s: (lücken_start, lücken_ende) in Sekunden
        gaps: list[tuple] = []
        i = 0
        while i < len(speech):
            if not speech[i]:
                j = i
                while j < len(speech) and not speech[j]:
                    j += 1
                if (j - i) * dt >= min_gap_s:
                    gaps.append((i * dt, j * dt))
                i = j
            else:
                i += 1

        # Akustische Regionen = Sprachblöcke zwischen den Lücken:
        # [0, gap0.start], [gap0.end, gap1.start], ..., [gapN.end, dauer]
        duration = len(speech) * dt
        regions: list[tuple] = []
        cursor = 0.0
        for gs, ge in gaps:
            if ge > cursor:
                regions.append((cursor, gs))
            cursor = max(cursor, ge)
        if duration > cursor + 0.02:
            regions.append((cursor, duration))

        def assign_region(t: float) -> int:
            """Region für einen Wort-Start.

            ZUERST Lücken prüfen: Liegt t in (bzw. exakt am Anfang) einer
            Stille-Lücke → Region NACH der Lücke (Modell-Kollaps: Start
            klebt an der Vorgänger-Grenze = Lücken-Anfang). Sonst Region,
            die t enthält."""
            for gs, ge in gaps:
                if gs - 0.03 <= t <= ge:
                    for ri, (rs, _re) in enumerate(regions):
                        if rs >= ge - 0.02:
                            return ri
                    break
            for ri, (rs, re) in enumerate(regions):
                if rs <= t <= re:
                    return ri
            for ri, (rs, _re) in enumerate(regions):
                if rs > t:
                    return ri
            return max(0, len(regions) - 1)

        out: list[dict] = []
        for wi, w in enumerate(words):
            item = dict(w)
            s = item.get("start")
            e = item.get("end")
            if s is None:
                s = 0.0
            nxt_s = words[wi + 1].get("start") if wi + 1 < len(words) else None
            zero_duration = (e is None or e <= s)
            # Wort der akustischen Region zuordnen (Start in Lücke →
            # Region NACH der Lücke), Start auf Region-Start anheben.
            ri = assign_region(s)
            rs, re = regions[ri] if regions else (0.0, duration)
            if s < rs:
                s = rs
            if zero_duration:
                # 0-Dauer-Kollaps: Ende = Ende der Start-Region. Mit
                # min_gap_s=0,25 verschmelzen Silben-Lücken desselben
                # Worts (< 0,25 s) bereits zu EINER Region — kein Merge
                # über Wortgrenzen nötig (sonst zieht der nächste
                # CLI-Start die Folgeregion mit rein).
                e = re
            elif e is not None and e > re:
                # gültiges CLI-Ende jenseits der Region → Region-Ende
                e = re
            # Reihenfolge wahren: nicht vor dem Vorgänger-Ende,
            # nicht über den nächsten CLI-Start hinaus.
            if out and s < out[-1].get("end", 0.0):
                s = out[-1]["end"]
            if nxt_s is not None and e > nxt_s:
                e = nxt_s
            if e <= s:
                e = s + 0.08
            item["start"], item["end"] = s, e
            out.append(item)
        return out
    except Exception:
        # Defensiv: nie verschlechtern
        return words


def _run_aligner(cli: str, model: str, wav: str, text: str, lang: str) -> str:
    """Führt den CLI-Aufruf aus, liefert Pfad zur Output-Datei.

    Läuft als Popen mit LIVE-stderr-Lesen: Jede ausgegebene Zeile wird in
    ``_JOB_STATUS`` registriert (echtes Lebenszeichen — die Webapp pollt
    /status, damit die UI keinen Fake-Progress zeigt). ggml-CLIs geben oft
    ``main: processing ...`` / ``progress = N%`` aus — wir parsen beides,
    sind aber tolerant: auch ohne Progress-Zeilen meldet /status die
    vergangene Zeit ('aktiv seit Xs').
    """
    import re

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_json = tf.name
    try:
        with _lock:
            _job_start()
            proc = subprocess.Popen(
                [cli, "-m", model, "-f", wav, "--align",
                 "--text", text, "--lang", lang, "-o", out_json],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            assert proc.stdout is not None
            prog_re = re.compile(r"(?:progress\s*[:=]?\s*(\d{1,3})\s*%|(\d{1,3})\s*%)")
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                _job_beat(line)
                m = prog_re.search(line)
                if m:
                    pct = int(m.group(1) or m.group(2) or 0)
                    _job_progress(min(pct, 100))
            rc = proc.wait(timeout=CLI_TIMEOUT_S)
            if rc != 0:
                _job_finish(error=f"CLI exit {rc}")
                raise RuntimeError(f"Aligner-CLI exit {rc}")
        _job_finish()
        return out_json
    except subprocess.TimeoutExpired:
        _job_finish(error="timeout")
        os.unlink(out_json)
        raise RuntimeError(f"Aligner-Timeout nach {CLI_TIMEOUT_S}s")
    except subprocess.CalledProcessError as exc:
        _job_finish(error="calledprocess")
        os.unlink(out_json)
        detail = (exc.stderr or "").strip()[-500:] or f"exit {exc.returncode}"
        raise RuntimeError(f"Aligner fehlgeschlagen: {detail}")
    except Exception:
        _job_finish(error="exception")
        os.unlink(out_json)
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "polyschnack-aligner/1.0"

    cli = ""
    model = ""

    # --- helpers -------------------------------------------------------
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # leiser
        pass

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            raise ValueError("Upload zu groß (max 512 MB)")
        return self.rfile.read(length)

    # --- routes --------------------------------------------------------
    def _device(self) -> str:
        """cuda|cpu — EHRLICHE Selbstauskunft (Fix 2026-08-15).

        VORHER: nur nvidia-smi -L geprüft (GPU im Container sichtbar) —
        das bewies NICHT, dass die ggml-Binary ein CUDA-Backend hat.
        Konsequenz: CPU-only-Builds meldeten 'cuda' und 60-min-Alignments
        dauerten Stunden. Jetzt: GPU sichtbar UND libggml-cuda.so vorhanden
        (= CUDA-Backend wirklich kompiliert).
        """
        import glob

        try:
            out = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                                 text=True, timeout=5)
            gpu_visible = out.returncode == 0 and bool(out.stdout.strip())
        except Exception:
            gpu_visible = False
        if not gpu_visible:
            return "cpu"
        cuda_lib = bool(glob.glob("/usr/local/lib/libggml-cuda*")
                        or glob.glob("/usr/local/lib/libggml_cuda*"))
        return "cuda" if cuda_lib else "cpu"

    def do_GET(self) -> None:
        if self.path == "/health":
            # Self-describing: die Webapp liest hier die Aligner-Features
            # für die Service-Diagnose (/api/services/status).
            # Ehrliche Selbstauskunft (verifiziert 08/2026): die
            # qwen3-forced-aligner-CLI (predict-woo/qwen3-asr.cpp,
            # cli/main.cpp -> alignment_to_json()) gibt NUR
            # {word, start, end} aus — KEIN confidence. Deshalb False,
            # nicht True: eine falsche Angabe hier hat die Diagnose
            # wiederholt in die Irre geführt. Der Parser reicht
            # confidence trotzdem durch, falls eine spätere CLI-Version
            # es liefert (defensiv, schadet nicht).
            self._send(200, {
                "status": "ok",
                "service": "aligner",
                "model": "qwen3-forced-aligner-0.6b-f16",
                "max_duration_s": MAX_AUDIO_S,
                "word_timestamps": True,
                "confidence": False,
                "languages": ["de", "en"],
                "device": self._device(),
                "max_upload_bytes": MAX_BODY_BYTES,
            })
        elif self.path == "/status":
            # Live-Lebenszeichen des Aligner-Prozesses (2026-08-15): die
            # Webapp pollt hier, damit die UI echten Fortschritt zeigt —
            # kein animierter Fake, sondern: aktiv seit Xs, letzte CLI-Zeile,
            # ggml-Progress % (falls die CLI es ausgibt).
            self._send(200, _job_snapshot())
        elif self.path == "/openapi.json":
            # OpenAPI-Spec für die Swagger-Doku (Dockerfile kopiert die
            # Datei nach /app/openapi.json — single source of truth).
            try:
                with open(_OPENAPI_PATH, "r", encoding="utf-8") as fh:
                    spec = fh.read()
            except OSError:
                self._send(404, {"error": "openapi.json nicht im Container"})
                return
            body = spec.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/docs":
            # Swagger-UI (CDN) — eingebettet, kein Node-Build nötig.
            html = _SWAGGER_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/audio/align":
            self._send(404, {"error": "not found"})
            return
        try:
            fields = self._parse_multipart()
            raw = fields.get("file")
            if not raw:
                self._send(422, {"error": "Feld 'file' fehlt (multipart/form-data)"})
                return
            text = fields.get("text") or ""
            if not text.strip():
                self._send(422, {"error": "Feld 'text' fehlt (Referenztext)"})
                return
            lang = fields.get("lang") or "de"

            with tempfile.TemporaryDirectory(prefix="align-") as tmp:
                src = os.path.join(tmp, "upload.bin")
                wav = os.path.join(tmp, "audio.wav")
                with open(src, "wb") as fh:
                    fh.write(raw)
                dur = _probe_duration_s(src)
                if dur > MAX_AUDIO_S:
                    self._send(422, {
                        "error": f"Audio zu lang: {dur:.0f}s (max {MAX_AUDIO_S:.0f}s pro Request) — "
                                 "bitte in Chunks schneiden und je Chunk den passenden Text senden",
                        "duration_s": dur,
                        "max_duration_s": MAX_AUDIO_S,
                    })
                    return
                _to_wav16k(src, wav)
                out_json = _run_aligner(self.cli, self.model, wav, text, lang)
                words = _parse_alignment(out_json, resolve=False)
                # Energie-Korrektur (2026-08-17): ordnet Wörter den
                # akustisch belegten Regionen zu — Stille gehört keinem
                # Wort. Behebt 0-Dauer-Kollaps bei künstlichen Pausen
                # (Karaoke-Sync). Danach _resolve_zero_duration als
                # Sicherheitsnetz für Wörter ohne gültiges Intervall.
                words = _resolve_zero_duration(_energy_refine(words, wav))
                os.unlink(out_json)
            self._send(200, {"words": words, "language": lang, "duration_s": dur})
        except ValueError as exc:
            self._send(413, {"error": str(exc)})
        except RuntimeError as exc:
            self._send(500, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — Wrapper muss immer antworten
            self._send(500, {"error": f"Interner Fehler: {exc}"})

    def _parse_multipart(self) -> dict:
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype or "boundary=" not in ctype:
            raise ValueError("Content-Type muss multipart/form-data mit boundary sein")
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
        body = self._read_body()
        fields: dict = {}
        for block in body.split(b"--" + boundary):
            if not block or block in (b"\r\n", b"--\r\n"):
                continue
            if b"\r\n\r\n" not in block:
                continue
            head, _, data = block.partition(b"\r\n\r\n")
            data = data.rstrip(b"\r\n")
            headers = {}
            for line in head.split(b"\r\n"):
                ls = line.decode(errors="replace")
                if ":" in ls:
                    k, v = ls.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            disp = headers.get("content-disposition", "")
            name = ""
            for part in disp.split(";"):
                part = part.strip()
                if part.startswith("name="):
                    name = part[5:].strip('"')
            if name == "file":
                fields["file"] = data
            elif name:
                fields[name] = data.decode(errors="replace").strip()
        return fields


def main() -> None:
    ap = argparse.ArgumentParser(description="PolySchnack Forced-Aligner-Service")
    ap.add_argument("--cli", default="qwen3-asr-cli", help="Pfad zur qwen3-asr-cli Binary")
    ap.add_argument("--model", default="/models/qwen3-forced-aligner-0.6b-f16.gguf")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5099)
    args = ap.parse_args()

    if not os.path.exists(args.model):
        print(f"[aligner] FEHLER: Modell nicht gefunden: {args.model}", file=sys.stderr)
        sys.exit(1)
    Handler.cli = args.cli
    Handler.model = args.model

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[aligner] Forced-Aligner-Service auf {args.host}:{args.port} "
          f"(Modell: {args.model}, CLI: {args.cli})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
