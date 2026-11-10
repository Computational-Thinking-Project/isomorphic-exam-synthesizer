"""Fail-closed network boundary for the local-only P4 Python runner.

Install before importing the application. This does not replace Auth, JWT or DB
dependencies. Docker isolation is an additional boundary, not implied by this guard.
"""
import ipaddress
import socket
from urllib.parse import urlsplit


def assert_local_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("P4 only accepts HTTP loopback endpoints")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in endpoint URLs are forbidden")


class LoopbackGuard:
    """Reject all non-loopback TCP connects; count attempts without logging secrets."""

    def __init__(self):
        self.blocked = 0
        self._connect = socket.socket.connect
        self._connect_ex = socket.socket.connect_ex

    def _check(self, sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            return
        try:
            allowed = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            self.blocked += 1
            raise PermissionError("P4 blocked a non-loopback network connection")

    def __enter__(self):
        guard = self

        def connect(sock, address):
            guard._check(sock, address)
            return guard._connect(sock, address)

        def connect_ex(sock, address):
            guard._check(sock, address)
            return guard._connect_ex(sock, address)

        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._connect
        socket.socket.connect_ex = self._connect_ex
