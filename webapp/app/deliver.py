"""Delivery der fertigen Transkription (Task D5) — E-Mail (smtplib) / WebDAV."""
from __future__ import annotations

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from .config import settings
from .crypto import decrypt


def deliver(rec, target) -> None:
    """Sende *rec* an *target*; wirft bei Fehlern (Status wird vom Caller gesetzt)."""
    cfg = json.loads(target.config or "{}")
    if target.kind == "email":
        _deliver_email(rec, cfg)
    elif target.kind == "webdav":
        _deliver_webdav(rec, cfg)
    else:
        raise RuntimeError(f"unbekanntes Delivery-Target: {target.kind}")


def _deliver_email(rec, cfg: dict) -> None:
    if not settings.POLYSCHNACK_SMTP_HOST:
        raise RuntimeError("SMTP nicht konfiguriert (POLYSCHNACK_SMTP_HOST)")
    to = cfg.get("to")
    if not to:
        raise RuntimeError("email-target ohne Empfänger (config.to)")
    msg = MIMEMultipart()
    msg["To"] = to
    msg["From"] = settings.POLYSCHNACK_SMTP_FROM or settings.POLYSCHNACK_SMTP_USER or "polyschnack@localhost"
    msg["Subject"] = f"Transkription: {rec.original_name}"
    msg.attach(MIMEText(rec.text or "", "plain", "utf-8"))
    for fname, payload, ctype in [
        (f"{rec.original_name}.txt", rec.text or "", "text/plain"),
        (f"{rec.original_name}.json", json.dumps({"text": rec.text}, ensure_ascii=False), "application/json"),
    ]:
        part = MIMEText(payload, ctype, "utf-8")
        part.add_header("Content-Disposition", "attachment", filename=fname)
        msg.attach(part)
    with smtplib.SMTP(settings.POLYSCHNACK_SMTP_HOST,
                      settings.POLYSCHNACK_SMTP_PORT or 587) as s:
        if settings.POLYSCHNACK_SMTP_USER:
            s.login(settings.POLYSCHNACK_SMTP_USER, settings.POLYSCHNACK_SMTP_PASS)
        s.send_message(msg)


def _deliver_webdav(rec, cfg: dict) -> None:
    url = (cfg.get("url") or "").rstrip("/")
    path = (cfg.get("path") or "").strip("/")
    if not url or not cfg.get("username") or not cfg.get("password"):
        raise RuntimeError("webdav-target unvollständig (url/username/password/path)")
    dest = f"{url}/{path}/{rec.original_name}.txt" if path else f"{url}/{rec.original_name}.txt"
    r = httpx.put(
        dest,
        auth=(cfg["username"], decrypt(cfg["password"])),
        content=(rec.text or "").encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()
