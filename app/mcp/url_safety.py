"""Validation for URLs handed to the remote retrieval service."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    pass


def validate_public_http_url(value: str) -> str:
    """Allow public HTTP(S) URLs while rejecting local and special targets.

    Parallel performs the actual fetch. This guard prevents obvious localhost,
    private-IP and local-name SSRF targets from being sent to that service.
    """
    if not isinstance(value, str) or len(value) > 4096:
        raise UnsafeURLError("URL must be a string no longer than 4096 characters")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Malformed URL") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeURLError("Only HTTP and HTTPS URLs are allowed")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("URL must have a public hostname and no credentials")
    if port is not None and not (1 <= port <= 65535):
        raise UnsafeURLError("Invalid URL port")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeURLError("Local hostnames cannot be fetched")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UnsafeURLError("Private, loopback, and reserved IP addresses cannot be fetched")

    return value.strip()
