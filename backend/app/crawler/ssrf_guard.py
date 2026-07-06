"""SSRF (Server-Side Request Forgery) guard for the crawler.

The crawler fetches user-supplied URLs, so without this a user could point it
at internal-only addresses - cloud metadata (169.254.169.254), the app's own
private services (*.railway.internal), loopback, or RFC-1918 networks - and
read the response back through the audit results.

`blocked_reason(url)` returns a human-readable reason string when a URL must
NOT be fetched, or None when it's a normal public URL that's safe to crawl.
It resolves the hostname and rejects the URL if ANY resolved address falls in
a private/reserved range (blocking on *any* internal IP also defeats hosts
that resolve to both a public and a private address).

Note: this checks DNS at call time; a determined attacker could still exploit
DNS rebinding (resolve public here, private when httpx connects a moment
later). Fully closing that needs pinning the resolved IP for the connection;
this guard stops the overwhelming majority of real-world SSRF (direct internal
URLs, discovered internal links, and redirects into internal space).
"""
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

# Exact hostnames that are always internal regardless of DNS.
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata"}

# Suffixes used for internal service discovery (Railway, k8s, docker-compose…).
_BLOCKED_SUFFIXES = (".internal", ".local", ".localhost")


def _hostname_is_internal(host: str) -> bool:
    h = host.lower().rstrip(".")
    if h in _BLOCKED_HOSTNAMES:
        return True
    return any(h.endswith(suffix) for suffix in _BLOCKED_SUFFIXES)


def _ip_is_internal(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable → treat as unsafe
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local     # 169.254.0.0/16 - cloud metadata lives here
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified    # 0.0.0.0
    )


def blocked_reason(url: str) -> Optional[str]:
    """Return why `url` is unsafe to fetch, or None if it's a public URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "unparseable URL"

    if parsed.scheme not in ("http", "https"):
        return f"scheme '{parsed.scheme}' is not allowed (only http/https)"

    host = parsed.hostname
    if not host:
        return "URL has no host"

    if _hostname_is_internal(host):
        return f"'{host}' is an internal hostname"

    # Literal IP in the URL - check it directly, no DNS needed.
    try:
        ipaddress.ip_address(host)
        return f"{host} is a private/reserved address" if _ip_is_internal(host) else None
    except ValueError:
        pass

    # Hostname → resolve and reject if ANY address is internal.
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Can't resolve → not an SSRF bypass; let the normal fetch fail on its own.
        return None

    for info in infos:
        ip = info[4][0]
        if _ip_is_internal(ip):
            return f"'{host}' resolves to internal address {ip}"
    return None
