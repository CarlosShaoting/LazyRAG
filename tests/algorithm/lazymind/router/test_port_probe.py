from __future__ import annotations

import asyncio
import socket

import pytest

from lazymind.router.core.port_probe import is_tcp_port_open


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_is_tcp_port_open_returns_true_for_listening_port():
    server = await asyncio.start_server(
        lambda _reader, writer: writer.close(),
        '127.0.0.1',
        0,
    )
    try:
        port = int(server.sockets[0].getsockname()[1])
        assert await is_tcp_port_open('127.0.0.1', port, timeout=0.2) is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_is_tcp_port_open_returns_false_for_closed_port():
    assert await is_tcp_port_open('127.0.0.1', _unused_local_port(), timeout=0.2) is False
