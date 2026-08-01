"""SSRF-Schutz für BYOK-Endpunkte (Task E1) — private Netze hart blocken."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

_PRIVATE = (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
)
_BLOCKED_HOSTS = ("localhost", "metadata.google.internal", "metadata")


def validate_llm_url(url: str) -> str:
    """Prüft, dass die URL auf einen öffentlichen http(s)-Host zeigt."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(422, "nur http(s)-URLs erlaubt")
    host = u.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise HTTPException(422, "private/loopback-Hosts sind nicht erlaubt")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except OSError:
            raise HTTPException(422, "Host nicht auflösbar")
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved \
            or any(ip in ipaddress.ip_network(n) for n in _PRIVATE):
        raise HTTPException(422, "private/loopback-Adressen sind nicht erlaubt")
    return url
