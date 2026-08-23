#!/usr/bin/env python3
"""PolySchnack Source-Separation-Service (crispr-sep) — schlanker HTTP-Wrapper.

Nur Python-Stdlib (kein FastAPI/pip) — der Container bleibt klein
(gleiches Muster wie aligner_server.py).

Endpoints:
  GET  /health                -> {"status", "backends", "models", ...}
  GET  /status                -> Live-Job-Status (Herzschlag der CLI)
  POST /v1/audio/separate     -> vocals.wav (audio/wav, 44.1 kHz stereo)
      multipart/form-data: file (Audio, beliebiges Format via ffmpeg),
                           backend ("htdemucs" | "mel-band-roformer")

Backends (Change 106):
  htdemucs           cstr/htdemucs-GGUF          (4 Stems, hier: vocals)
  mel-band-roformer  cstr/mel-band-roformer-vocals-GGUF (vocals/other)

Ehrlicher Fehlerpfad: liefert der CLI-Lauf keine vocals.wav (leere
Separation, Modell fehlt), antworten wir mit 422 + Grund — kein
Fake-„done". Nur ein Job gleichzeitig (Lock): die ggml-Modelle sind
resident geladen, parallele Läufe würden VRAM/RAM sprengen.
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

MAX_BODY_BYTES = 512 * 1024 * 1024  # 512 MB Upload-Limit
CLI_TIMEOUT_S = 3600  # 90-min-Audio: CPU-Läufe sind lang (Change 106, Risiko)

HTDEMUCS_MODEL = os.getenv("SEP_HTDEMUCS_MODEL", "/models/htdemucs-f16.gguf")
MELBAND_MODEL = os.getenv("SEP_MELBAND_MODEL", "/models/mel-band-roformer-vocals-f16.gguf")
BACKEND_MODELS = {
    "htdemucs": HTDEMUCS_MODEL,
    "mel-band-roformer": MELBAND_MODEL,
}
CRISPASR_BIN = os.getenv("CRISPASR_BIN", "crispasr")

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Live-Job-Status (Muster aligner_server.py): ECHTE Lebenszeichen der CLI.
# ---------------------------------------------------------------------------
_JOB_STATUS: dict = {
    "active": False,
    "backend": None,
    "started_at": None,
    "last_beat_at": None,
    "last_line": "",
    "error": None,
}
_JOB_LOCK = threading.Lock()


def _job_start(backend: str) -> None:
    with _JOB_LOCK:
        _JOB_STATUS.update(
            active=True, backend=backend, started_at=time.time(),
            last_beat_at=time.time(), last_line="", error=None,
        )


def _job_beat(line: str) -> None:
    with _JOB_LOCK:
        _JOB_STATUS["last_beat_at"] = time.time()
        _JOB_STATUS["last_line"] = line[-160:]


def _job_finish(error: str | None = None) -> None:
    with _JOB_LOCK:
        _JOB_STATUS.update(active=False, backend=None, error=error)


def _job_snapshot() -> dict:
    with _JOB_LOCK:
        snap = dict(_JOB_STATUS)
    if snap["started_at"]:
        snap["elapsed_s"] = round(time.time() - snap["started_at"], 1)
    if snap["last_beat_at"]:
        snap["last_beat_ago_s"] = round(time.time() - snap["last_beat_at"], 1)
    return snap


# ---------------------------------------------------------------------------
# CLI-Aufruf
# ---------------------------------------------------------------------------
def _to_wav44100(src: str, dst: str) -> None:
    """Beliebiges Eingabeformat -> 44.1 kHz Stereo-WAV (htdemucs-Anforderung)."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "2", "-ar", "44100", dst],
        capture_output=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg-Konvertierung fehlgeschlagen: {r.stderr.decode(errors='replace')[-300:]}")


def _run_separate(backend: str, model: str, wav_in: str, out_dir: str) -> str:
    """Führt crispasr --separate aus; liefert den Pfad der vocals.wav."""
    cmd = [
        CRISPASR_BIN, "--separate", "--backend", backend,
        "-m", model, "-f", wav_in,
        "--stems", "vocals", "--sep-output-dir", out_dir,
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            _job_beat(line)
    proc.wait(timeout=CLI_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(f"crispasr --separate exit {proc.returncode} (letzte Zeile: {_JOB_STATUS['last_line']})")

    # Ausgabe: <input>_vocals.wav im out_dir (mel-band-roformer: vocals/other,
    # htdemucs: drums/bass/other/vocals — wir erbitten nur vocals).
    candidates = [f for f in os.listdir(out_dir) if f.endswith("_vocals.wav")]
    if not candidates:
        raise RuntimeError(f"keine vocals.wav erzeugt (Backend {backend} lieferte nichts)")
    vocals = os.path.join(out_dir, candidates[0])
    if os.path.getsize(vocals) < 1024:
        raise RuntimeError(f"vocals.wav ist leer (nur {os.path.getsize(vocals)} Bytes) — Separation ohne Ergebnis")
    return vocals


# ---------------------------------------------------------------------------
# HTTP-Server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict | bytes, ctype: str = "application/json") -> None:
        if isinstance(payload, bytes):
            body = payload
            ctype = ctype or "application/octet-stream"
        else:
            body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # leiser
        pass

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            raise ValueError("Body zu gross (Limit 512 MB)")
        return self.rfile.read(length)

    def _parse_multipart(self) -> dict:
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype or "boundary=" not in ctype:
            raise ValueError("Content-Type muss multipart/form-data mit boundary sein")
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
        body = self._read_body()
        fields: dict = {}
        for block in body.split(b"--" + boundary):
            if not block or block in (b"--", b"--\r\n"):
                continue
            header, _, content = block.partition(b"\r\n\r\n")
            if not header or not content:
                continue
            content = content.rstrip(b"\r\n")
            name = ""
            filename = None
            for line in header.decode(errors="replace").split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    import re
                    m = re.search(r'name="([^"]+)"', line)
                    if m:
                        name = m.group(1)
                    m = re.search(r'filename="([^"]*)"', line)
                    if m and m.group(1):
                        filename = m.group(1)
            if filename:
                fields[name] = content
            else:
                fields[name] = content.decode(errors="replace")
        return fields

    # -- GET ----------------------------------------------------------------
    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/health":
            models = {b: os.path.exists(m) for b, m in BACKEND_MODELS.items()}
            self._send(200, {
                "status": "ok",
                "service": "separator",
                "backends": list(BACKEND_MODELS),
                "models": models,
                "missing_models": [b for b, ok in models.items() if not ok],
            })
        elif self.path.split("?")[0] == "/status":
            self._send(200, _job_snapshot())
        else:
            self._send(404, {"error": "nicht gefunden"})

    # -- POST ---------------------------------------------------------------
    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/v1/audio/separate":
            self._send(404, {"error": "nicht gefunden"})
            return
        try:
            fields = self._parse_multipart()
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return

        audio = fields.get("file")
        backend = fields.get("backend") or "htdemucs"
        if audio is None:
            self._send(422, {"error": "Feld 'file' fehlt (multipart/form-data)"})
            return
        if backend not in BACKEND_MODELS:
            self._send(422, {"error": f"Unbekanntes Backend '{backend}' — erlaubt: {', '.join(BACKEND_MODELS)}"})
            return
        model = BACKEND_MODELS[backend]
        if not os.path.exists(model):
            self._send(422, {"error": f"Modell fehlt: {model} (Backend {backend} deaktiviert)"})
            return

        if not _lock.acquire(blocking=False):
            self._send(409, {"error": "Separation läuft bereits (ein Job gleichzeitig)"})
            return
        try:
            _job_start(backend)
            with tempfile.TemporaryDirectory(prefix="crispr-sep-") as td:
                in_raw = os.path.join(td, "input.raw")
                with open(in_raw, "wb") as f:
                    f.write(audio)
                in_wav = os.path.join(td, "input.wav")
                out_dir = os.path.join(td, "out")
                os.makedirs(out_dir, exist_ok=True)
                _to_wav44100(in_raw, in_wav)
                vocals = _run_separate(backend, model, in_wav, out_dir)
                with open(vocals, "rb") as f:
                    vocals_bytes = f.read()
            _job_finish()
            self._send(200, vocals_bytes, "audio/wav")
        except Exception as exc:
            _job_finish(str(exc))
            self._send(422, {"error": str(exc)[:300]})


def main() -> None:
    ap = argparse.ArgumentParser(description="PolySchnack Source-Separation-Service")
    ap.add_argument("--port", type=int, default=int(os.getenv("SEP_PORT", "5100")))
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    # Start-Sanity: Binary vorhanden? (klare Meldung statt späterem 422-Rätsel)
    bin_ok = subprocess.run(
        ["sh", "-c", f"command -v {CRISPASR_BIN}"], capture_output=True,
    ).returncode == 0
    print(f"[sep] Binary '{CRISPASR_BIN}': {'ok' if bin_ok else 'FEHLT — Separation wird 422 liefern'}")
    for backend, model in BACKEND_MODELS.items():
        print(f"[sep] Backend {backend}: {'vorhanden' if os.path.exists(model) else 'FEHLT'} ({model})")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[sep] Server auf {args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
