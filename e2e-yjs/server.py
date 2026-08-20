"""E2E-Test-Server für Yjs-Sync (Change 053): minimaler ASGI-Host ohne Auth."""
import sys

sys.path.insert(0, "/opt/data/pk-asr/webapp")

from app.yjs.rooms import build_asgi_server  # noqa: E402

app = build_asgi_server()
