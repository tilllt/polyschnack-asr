"""Yjs-Kollaboration (Change 053): Room-Verwaltung + Snapshot-Persistenz.

Ein Room je Recording-UID. Doc-Struktur:
    segments: Map<str(idx), Text>   — Segment-Texte (Index = Segment-Position)
    meta:     Map                   — recording_uid, language, updated_at

Persistenz: ein binärer Yjs-Update-Snapshot je Room unter YJS_DATA_DIR
(Default ./DATA/yjs). Snapshot wird beim Room-Start geladen und bei jeder
Änderung (doc.observe) geschrieben — Update-Logging ist kompakt, kein
Voll-Serialize nötig (get_update wächst nur um neue Änderungen, wenn man
den Update-Fluss anhängt; hier: inkrementelle Appends in eine Log-Datei).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from pycrdt import Doc, Map, Text
from pycrdt.websocket.asgi_server import ASGIServer
from pycrdt.websocket.websocket_server import WebsocketServer

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("YJS_DATA_DIR", "./DATA/yjs"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_lock = asyncio.Lock()
_rooms: dict[str, Doc] = {}
_writer_tasks: dict[str, asyncio.Task] = {}


def _snapshot_path(room_name: str) -> Path:
    # Room-Namen sind Recording-UIDs (hex) — Dateinamen-sicher.
    return DATA_DIR / f"{room_name}.bin"


class FileProvider:
    """Lädt/appendet Yjs-Updates für einen Room als Snapshot-Datei.

    Konsistenz-Regel: Beim ersten Start (kein Snapshot) wird der komplette
    Doc-State (get_update) persistiert — damit sind Struktur und
    Initialdaten (segments-/meta-Map) Teil des Snapshots. Danach appendet
    observe nur noch Deltas.

    Format: Length-prefixed Blöcke ([4B big-endian Länge][Update]). Yjs
    verarbeitet konkatenierte Updates NICHT als ein einzelnes Payload
    (nur das erste greift) — deshalb werden die Blöcke einzeln mit
    apply_update angewandt. Beim Laden wird observe unterdrückt
    (_loading), sonst würden die geladenen Updates erneut in den Snapshot
    geschrieben und die Datei bei jedem Start dupliziert wachsen.
    """

    def __init__(self, doc: Doc, path: str):
        self.doc = doc
        self.path = path
        self._snapshot = _snapshot_path(path)
        self._stop = False
        self._loading = False

    def start(self) -> None:
        self._loading = True
        try:
            snapshots = self._load_snapshots()
            if snapshots:
                for upd in snapshots:
                    self.doc.apply_update(upd)
                log.info("Yjs-Room %s: %d Snapshot-Block(s) geladen (%d B)",
                         self.path, len(snapshots), self._snapshot.stat().st_size)
            else:
                # Erster Start: Voll-State persistieren (Struktur + Initialdaten).
                self._write_snapshot(self.doc.get_update())
        finally:
            self._loading = False
        self.doc.observe(self._on_change)

    def stop(self) -> None:
        self._stop = True

    # pycrdt-websocket nutzt die Provider-Factory als `async with` (YRoom._run_provider).
    async def __aenter__(self) -> "FileProvider":
        self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        self.stop()

    def _load_snapshots(self) -> list[bytes]:
        if not self._snapshot.exists():
            return []
        data = self._snapshot.read_bytes()
        out: list[bytes] = []
        off = 0
        while off + 4 <= len(data):
            n = int.from_bytes(data[off:off + 4], "big")
            off += 4
            if off + n > len(data):
                break  # beschädigter Tail — ignorieren
            out.append(data[off:off + n])
            off += n
        return out

    def _write_snapshot(self, update: bytes) -> None:
        with self._snapshot.open("ab") as f:
            f.write(len(update).to_bytes(4, "big"))
            f.write(update)
            f.flush()

    def _on_change(self, event) -> None:
        if self._stop or self._loading:
            return
        update = getattr(event, "update", None)
        if not update:
            return
        try:
            self._write_snapshot(update)
        except Exception:
            log.exception("Yjs-Room %s: Snapshot-Schreiben fehlgeschlagen", self.path)


def _room_factory(doc: Doc | None = None, path: str | None = None):
    """RoomFactory für WebsocketServer: Doc + FileProvider je Room-Name.

    WICHTIG (Review 2026-08-20): Das von YRoom übergebene `doc` verwenden —
    das ist das Doc, das mit den Clients synchronisiert wird. Ein eigenes
    Doc hier wäre vom Room-State entkoppelt und die Snapshot-Persistenz
    würde ins Leere laufen.

    y-websocket-Clients hängen den Room-Namen an die Basis-URL an
    (z.B. /yjs/<recordingUid>) — der Pfad IST der Room-Name. Für den
    Snapshot-Dateinamen wird er normalisiert.
    """
    room_key = (path or "default").replace("/yjs/", "").replace("/", "_")
    ydoc = doc if doc is not None else Doc()
    if ydoc.get("segments", type=Map) is None:
        ydoc["segments"] = Map()
    if ydoc.get("meta", type=Map) is None:
        ydoc["meta"] = Map()
    return FileProvider(ydoc, room_key)


_server: WebsocketServer | None = None


def get_server() -> WebsocketServer:
    """Lazy-Singleton des Yjs-WebsocketServers (ein Prozess, ein Server)."""
    global _server
    if _server is None:
        _server = WebsocketServer(
            auto_clean_rooms=True,
            provider_factory=lambda doc=None, log=None, path=None: _room_factory(doc, path),
        )
    return _server


class _YjsASGI:
    """ASGI-Wrapper: startet/stoppt den WebsocketServer über Lifespan-Events
    (pycrdt-websocket macht das nicht selbst) und delegiert alles andere."""

    def __init__(self, asgi_app, on_connect=None, on_disconnect=None):
        self.asgi_app = asgi_app
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self._start_task = None

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    # start() ist ein blockierender Server-Task (wartet bis
                    # stop) → als Task starten, auf "bereit" warten.
                    _task = asyncio.create_task(get_server().start())
                    self._start_task = _task
                    await get_server().started.wait()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    try:
                        await get_server().stop()
                    finally:
                        if self._start_task and not self._start_task.done():
                            self._start_task.cancel()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            await self.asgi_app(scope, receive, send)


def build_asgi_server(on_connect=None, on_disconnect=None) -> ASGIServer:
    """ASGI-App für FastAPI-Mount: app.mount('/yjs', build_asgi_server())."""
    return _YjsASGI(
        ASGIServer(get_server(), on_connect=on_connect, on_disconnect=on_disconnect),
        on_connect=on_connect,
        on_disconnect=on_disconnect,
    )
