#!/usr/bin/env python3
"""Entry point for the optimized PolySchnack v3 server.

Run with::

    python server.py                 # uvicorn defaults
    POLYSNACK_USE_GPU=true python server.py
    POLYSNACK_PORT=5093 python server.py

Or directly with uvicorn::

    uvicorn polyschnack_service.main:app --host 0.0.0.0 --port 5092
"""
from __future__ import annotations
import os

import uvicorn

from polyschnack_service.config import _getenv


def main() -> None:
    host = _getenv("HOST", "0.0.0.0")
    port = int(_getenv("PORT", "5092"))
    workers = int(_getenv("UVICORN_WORKERS", "1"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run(
        "polyschnack_service.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()
