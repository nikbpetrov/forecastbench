"""Socket-level no-network guard for the test suite.

Real network access is blocked by default so an accidentally-unmocked HTTP call fails loudly
and deterministically instead of hitting a live API. Connections to loopback are allowed (some
libraries open local sockets). Tests that genuinely need the network opt in with
``@pytest.mark.live``; the autouse fixture in ``conftest.py`` skips the block for them.
"""

from __future__ import annotations

import socket

# Loopback forms that are always allowed (some libraries open local sockets).
_ALLOWED_EXACT = {"::1", "localhost", "0.0.0.0", "", None}

_real_socket = socket.socket


def _is_local(host) -> bool:
    """Whether a connection target is loopback/local and may be allowed."""
    if host in _ALLOWED_EXACT:
        return True
    return isinstance(host, str) and host.startswith("127.")


class BlockedNetworkError(RuntimeError):
    """Raised when test code attempts a non-local network connection.

    Note: this guards the Python ``socket`` layer, which covers ``requests``/``urllib`` and
    most clients. It does not intercept native (C-core) transports such as gRPC — those are kept
    offline in tests by the lazy-import/fake-secrets fixtures instead (no client is constructed).
    """


class _GuardedSocket(_real_socket):
    """A socket that refuses to connect to non-loopback addresses."""

    def connect(self, address):  # noqa: D102 - thin override
        self._guard(address)
        return super().connect(address)

    def connect_ex(self, address):  # noqa: D102 - thin override
        self._guard(address)
        return super().connect_ex(address)

    @staticmethod
    def _guard(address) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if not _is_local(host):
            raise BlockedNetworkError(
                f"Network access to {host!r} blocked in tests. Mock the HTTP call, or mark the "
                "test @pytest.mark.live if it must reach the network."
            )


def install() -> None:
    """Replace ``socket.socket`` with the guarded subclass."""
    socket.socket = _GuardedSocket


def uninstall() -> None:
    """Restore the real ``socket.socket``."""
    socket.socket = _real_socket
